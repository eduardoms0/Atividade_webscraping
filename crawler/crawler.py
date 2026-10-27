#!/usr/bin/env python3
"""Crawler paginado de HTML do arXiv, opção 3 da atividade acadêmica.

Instalação: python -m pip install -r requirements.txt
Coleta real: python crawler.py
Reprodução sem rede: python crawler.py --offline --saida resultado_offline
"""

import argparse
import csv
import hashlib
import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin, urlparse
from urllib.request import Request, urlopen
from urllib.robotparser import RobotFileParser

from bs4 import BeautifulSoup

BASE = 'https://arxiv.org'
ALVO = BASE + '/list/cs.AI/recent'
AGENTE = 'CrawlerAcademicoArxiv/1.0'
RAIZ = Path(__file__).resolve().parent
CAMPOS = ['id_arxiv', 'titulo', 'data_anuncio', 'assunto_principal',
          'assuntos', 'url_resumo', 'url_pdf', 'pagina_origem', 'coletado_em']
MESES = dict(zip('Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec'.split(), range(1, 13)))


def agora():
    """Horário UTC explícito para rastrear a coleta, separado da data do anúncio."""
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def texto(elemento):
    # get_text com separador preserva palavras em tags aninhadas; split remove espaços extras.
    return ' '.join(elemento.get_text(' ', strip=True).split()) if elemento else ''


def sem_rotulo(elemento, rotulo):
    return re.sub(r'^' + re.escape(rotulo) + r'\s*:\s*', '', texto(elemento), flags=re.I)


def data_cabecalho(cabecalho):
    """Converte a data da seção sem depender do idioma configurado no computador."""
    achado = re.search(r'(\d{1,2})\s+([A-Z][a-z]{2})\s+(\d{4})', texto(cabecalho))
    if not achado or achado[2] not in MESES:
        return ''
    return datetime(int(achado[3]), MESES[achado[2]], int(achado[1])).date().isoformat()


def analisar_html(html, url, coletado_em):
    """Parser independente da rede. Retorna somente metadados bibliográficos."""
    soup = BeautifulSoup(html, 'html.parser')
    lista = soup.select_one('dl#articles') or soup.find('dl')
    if lista is None:
        raise ValueError('Lista de artigos ausente: HTML alterado, erro ou bloqueio do site.')
    registros = []
    for dt in lista.find_all('dt'):
        # O href estável evita depender de IDs/classes gerados para cada artigo.
        link = dt.select_one('a[href^="/abs/"]')
        if link is None:
            link = dt.find('a', href=re.compile(r'^https://arxiv\.org/abs/'))
        # Um zip(dt, dd) deslocaria todos os pares se um dd estivesse ausente.
        # Interrompemos no próximo dt para não atribuir os dados de outro artigo.
        dd = dt.find_next_sibling(['dt', 'dd'])
        if link is None or dd is None or dd.name != 'dd':
            logging.warning('Registro ignorado: link do resumo ou bloco dd ausente.')
            continue
        titulo = sem_rotulo(dd.select_one('.list-title'), 'Title')
        if not titulo:
            # Fallback para uma tag de título sem a classe list-title.
            rotulo = dd.find(string=re.compile(r'^\s*Title\s*:', re.I))
            titulo = sem_rotulo(rotulo.parent, 'Title') if rotulo else ''
            if not titulo and rotulo and rotulo.parent.parent != dd:
                titulo = sem_rotulo(rotulo.parent.parent, 'Title')
        if not titulo:
            logging.warning('Registro ignorado por não possuir título: %s', link.get('href'))
            continue
        assuntos_tag = dd.select_one('.list-subjects')
        assuntos = sem_rotulo(assuntos_tag, 'Subjects')
        principal = texto(dd.select_one('.primary-subject')) or assuntos.split(';')[0].strip()
        # A data pertence à seção do anúncio; não é a data da primeira submissão.
        cabecalho = dt.find_previous(['h3', 'h4'])
        resumo = urljoin(BASE, link['href'])
        identificador = urlparse(resumo).path.removeprefix('/abs/')
        pdf = dt.select_one('a[href^="/pdf/"]')
        registros.append({
            'id_arxiv': identificador, 'titulo': titulo,
            'data_anuncio': data_cabecalho(cabecalho),
            'assunto_principal': principal, 'assuntos': assuntos,
            'url_resumo': resumo, 'url_pdf': urljoin(BASE, pdf['href']) if pdf else '',
            'pagina_origem': url, 'coletado_em': coletado_em,
        })
    if not registros:
        raise ValueError('Nenhum registro válido: verifique se a estrutura HTML mudou.')
    return registros


class ClienteHTTP:
    """Requisições sequenciais, timeout e retentativas limitadas."""

    def __init__(self):
        self.intervalo = 15.0
        self.ultima = None

    def buscar(self, url):
        for tentativa in range(3):
            if self.ultima is not None:
                time.sleep(max(0, self.intervalo - (time.monotonic() - self.ultima)))
            self.ultima = time.monotonic()
            try:
                pedido = Request(url, headers={'User-Agent': AGENTE, 'Accept': 'text/html,text/plain'})
                with urlopen(pedido, timeout=30) as resposta:
                    return resposta.read().decode(resposta.headers.get_content_charset() or 'utf-8')
            except HTTPError as erro:
                if erro.code not in (429, 500, 502, 503, 504) or tentativa == 2:
                    raise
                # Só repetimos falhas temporárias; não contornamos bloqueios 401/403.
                espera = erro.headers.get('Retry-After', '')
                if espera.isdigit():
                    time.sleep(max(self.intervalo, int(espera)))
                logging.warning('HTTP %s. Nova tentativa com intervalo.', erro.code)
            except (URLError, TimeoutError):
                if tentativa == 2:
                    raise
                logging.warning('Falha temporária de rede; repetindo com intervalo.')
        raise RuntimeError('Não foi possível obter a página.')


def coletar(limite, por_pagina, pasta):
    cliente = ClienteHTTP()
    robots_texto = cliente.buscar(BASE + '/robots.txt')
    robots = RobotFileParser()
    robots.parse(robots_texto.splitlines())
    cliente.intervalo = max(15, robots.crawl_delay(AGENTE) or 0)
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / 'robots.txt').write_text(robots_texto, encoding='utf-8')
    registros, vistos, paginas = [], set(), []
    for numero in range(20):  # Limite de segurança: até 20 páginas, sem loop infinito.
        url = ALVO + '?' + urlencode({'skip': numero * por_pagina, 'show': por_pagina})
        if not robots.can_fetch(AGENTE, url):
            raise PermissionError('A consulta não é permitida pelo robots.txt atual.')
        logging.info('Coletando %s', url)
        html = cliente.buscar(url)
        instante = agora()
        lote = analisar_html(html, url, instante)
        arquivo = f'pagina_{numero:03d}.html'
        dados = html.encode('utf-8')
        (pasta / arquivo).write_bytes(dados)
        paginas.append({'arquivo': arquivo, 'url': url, 'coletado_em': instante,
                        'sha256': hashlib.sha256(dados).hexdigest(), 'registros_validos': len(lote)})
        antes = len(registros)
        for registro in lote:
            if registro['id_arxiv'] not in vistos:
                vistos.add(registro['id_arxiv'])
                registros.append(registro)
        if len(registros) >= limite:
            break
        if len(registros) == antes:
            raise ValueError('Página repetida: a paginação não avançou.')
    else:
        raise ValueError('Limite de páginas alcançado antes da quantidade solicitada.')
    (pasta / 'manifesto.json').write_text(json.dumps({
        'alvo': ALVO, 'paginas': paginas, 'intervalo_segundos': cliente.intervalo,
        'limite_solicitado': limite,
    }, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return registros[:limite]


def reproduzir(pasta, limite):
    """Reexecuta o mesmo parser sobre respostas HTML originais, verificadas por hash."""
    manifesto = json.loads((pasta / 'manifesto.json').read_text(encoding='utf-8'))
    registros, vistos = [], set()
    for pagina in manifesto['paginas']:
        dados = (pasta / pagina['arquivo']).read_bytes()
        if hashlib.sha256(dados).hexdigest() != pagina['sha256']:
            raise ValueError('HTML diferente do original: ' + pagina['arquivo'])
        for r in analisar_html(dados.decode('utf-8'), pagina['url'], pagina['coletado_em']):
            if r['id_arxiv'] not in vistos:
                vistos.add(r['id_arxiv'])
                registros.append(r)
        if len(registros) >= limite:
            break
    return registros[:limite]


def exportar(registros, pasta):
    pasta.mkdir(parents=True, exist_ok=True)
    # BOM e separador ; facilitam a abertura no Excel em português.
    with (pasta / 'editais_extraidos.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=CAMPOS, delimiter=';')
        writer.writeheader()
        writer.writerows(registros)
    (pasta / 'editais_extraidos.json').write_text(
        json.dumps(registros, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--limite', type=int, default=50, help='Quantidade de registros (mínimo 30).')
    parser.add_argument('--por-pagina', type=int, default=25, choices=[25, 50, 100])
    parser.add_argument('--offline', action='store_true', help='Usar HTML real salvo, sem acessar a rede.')
    parser.add_argument('--saida', type=Path, default=RAIZ, help='Diretório dos arquivos gerados.')
    parser.add_argument('--paginas', type=Path, default=RAIZ / 'paginas', help='Diretório dos snapshots.')
    args = parser.parse_args()
    if not 30 <= args.limite <= 500:
        parser.error('--limite deve estar entre 30 e 500.')
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    try:
        registros = (reproduzir(args.paginas, args.limite) if args.offline else
                     coletar(args.limite, args.por_pagina, args.paginas))
        if len(registros) < args.limite:
            raise ValueError(f'Só há {len(registros)} registros; solicitados {args.limite}.')
        exportar(registros, args.saida)
    except (OSError, ValueError, URLError, TimeoutError) as erro:
        logging.error('%s', erro)
        return 1
    logging.info('Concluído: %s registros únicos em %s', len(registros), args.saida.resolve())
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
