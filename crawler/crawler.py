#!/usr/bin/env python3
"""Coleta editais de pregão eletrônico publicados no PNCP."""

import argparse
import csv
import hashlib
import json
import logging
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

BASE = 'https://pncp.gov.br'
ALVO = BASE + '/api/consulta/v1/contratacoes/publicacao'
RAIZ = Path(__file__).resolve().parent
MODALIDADE = 6  # Pregão - Eletrônico, conforme o retorno da API do PNCP.
CAMPOS = [
    'id_pncp', 'numero_compra', 'processo', 'objeto', 'orgao', 'cnpj_orgao',
    'uf', 'municipio', 'modalidade', 'situacao', 'data_publicacao',
    'data_abertura_proposta', 'data_encerramento_propostas', 'valor_estimado',
    'url_edital', 'pagina_origem', 'coletado_em',
]


def agora():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def ler_resposta(texto):
    """Lê JSON do PNCP e informa conteúdo legível quando a API retorna HTML de erro."""
    try:
        return json.loads(texto)
    except json.JSONDecodeError as erro:
        mensagem = ' '.join(BeautifulSoup(texto, 'html.parser').get_text(' ', strip=True).split())
        detalhe = f' Resposta recebida: {mensagem[:300]}' if mensagem else ''
        raise ValueError(f'A API do PNCP não retornou JSON válido.{detalhe}') from erro


def analisar_resposta(payload, url, coletado_em):
    """Normaliza os campos do PNCP, tolerando campos opcionais ausentes."""
    if not isinstance(payload, dict) or not isinstance(payload.get('data'), list):
        raise ValueError('Resposta inválida da API do PNCP: campo data ausente ou inválido.')

    registros = []
    for item in payload['data']:
        if not isinstance(item, dict):
            logging.warning('Registro ignorado: formato inesperado.')
            continue
        identificador = str(item.get('numeroControlePNCP') or '').strip()
        objeto = str(item.get('objetoCompra') or '').strip()
        if not identificador or not objeto:
            logging.warning('Registro ignorado: identificador PNCP ou objeto ausente.')
            continue

        orgao = item.get('orgaoEntidade')
        orgao = orgao if isinstance(orgao, dict) else {}
        unidade = item.get('unidadeOrgao')
        unidade = unidade if isinstance(unidade, dict) else {}
        cnpj = str(orgao.get('cnpj') or '').strip()
        ano = item.get('anoCompra')
        sequencial = item.get('sequencialCompra')
        url_edital = (
            f'{BASE}/app/editais/{cnpj}/{ano}/{sequencial}'
            if cnpj and ano is not None and sequencial is not None else ''
        )
        registros.append({
            'id_pncp': identificador,
            'numero_compra': str(item.get('numeroCompra') or ''),
            'processo': str(item.get('processo') or ''),
            'objeto': objeto,
            'orgao': str(orgao.get('razaoSocial') or ''),
            'cnpj_orgao': cnpj,
            'uf': str(unidade.get('ufSigla') or ''),
            'municipio': str(unidade.get('municipioNome') or ''),
            'modalidade': str(item.get('modalidadeNome') or ''),
            'situacao': str(item.get('situacaoCompraNome') or ''),
            'data_publicacao': str(item.get('dataPublicacaoPncp') or ''),
            'data_abertura_proposta': str(item.get('dataAberturaProposta') or ''),
            'data_encerramento_propostas': str(item.get('dataEncerramentoProposta') or ''),
            'valor_estimado': item.get('valorTotalEstimado'),
            'url_edital': url_edital,
            'pagina_origem': url,
            'coletado_em': coletado_em,
        })
    return registros


class ClienteHTTP:
    """Cliente sequencial com timeout e retentativas limitadas."""

    def buscar(self, url):
        for tentativa in range(3):
            try:
                pedido = Request(
                    url,
                    headers={
                        'User-Agent': 'AtividadeAcademicaPNCP/1.0',
                        'Accept': 'application/json, text/html',
                    },
                )
                with urlopen(pedido, timeout=30) as resposta:
                    return resposta.read().decode(
                        resposta.headers.get_content_charset() or 'utf-8'
                    )
            except HTTPError as erro:
                if erro.code not in (429, 500, 502, 503, 504) or tentativa == 2:
                    raise
                espera = erro.headers.get('Retry-After', '')
                time.sleep(max(2, int(espera)) if espera.isdigit() else 2)
                logging.warning('HTTP %s. Nova tentativa.', erro.code)
            except (URLError, TimeoutError):
                if tentativa == 2:
                    raise
                time.sleep(2)
                logging.warning('Falha temporária de rede; repetindo a consulta.')
        raise RuntimeError('Não foi possível consultar a API do PNCP.')


def coletar(limite, por_pagina, pasta):
    hoje = date.today()
    data_inicial = (hoje - timedelta(days=30)).strftime('%Y%m%d')
    data_final = hoje.strftime('%Y%m%d')
    pasta.mkdir(parents=True, exist_ok=True)
    registros, vistos, paginas = [], set(), []

    for numero in range(1, 21):
        parametros = {
            'dataInicial': data_inicial,
            'dataFinal': data_final,
            'codigoModalidadeContratacao': MODALIDADE,
            'pagina': numero,
            'tamanhoPagina': por_pagina,
        }
        url = ALVO + '?' + urlencode(parametros)
        logging.info('Consultando %s', url)
        texto_resposta = ClienteHTTP().buscar(url)
        payload = ler_resposta(texto_resposta)
        instante = agora()
        lote = analisar_resposta(payload, url, instante)

        nome_arquivo = f'pagina_{numero:03d}.json'
        dados = (json.dumps(payload, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
        (pasta / nome_arquivo).write_bytes(dados)
        paginas.append({
            'arquivo': nome_arquivo,
            'url': url,
            'coletado_em': instante,
            'sha256': hashlib.sha256(dados).hexdigest(),
            'registros_validos': len(lote),
        })
        quantidade_anterior = len(registros)
        for registro in lote:
            if registro['id_pncp'] not in vistos:
                vistos.add(registro['id_pncp'])
                registros.append(registro)
        if len(registros) >= limite:
            break
        if len(registros) == quantidade_anterior:
            raise ValueError('A paginação não avançou ou não há mais editais no período consultado.')
        total_paginas = payload.get('totalPaginas')
        if isinstance(total_paginas, int) and numero >= total_paginas:
            break
        time.sleep(1)
    else:
        raise ValueError('Limite de páginas alcançado antes da quantidade solicitada.')

    if len(registros) < limite:
        raise ValueError(
            f'O PNCP retornou apenas {len(registros)} editais no período; '
            f'{limite} foram solicitados.'
        )
    (pasta / 'manifesto.json').write_text(json.dumps({
        'alvo': ALVO,
        'modalidade': 'Pregão - Eletrônico',
        'codigo_modalidade': MODALIDADE,
        'data_inicial': data_inicial,
        'data_final': data_final,
        'paginas': paginas,
        'limite_solicitado': limite,
    }, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return registros[:limite]


def reproduzir(pasta, limite):
    """Reprocessa as respostas JSON salvas, validando seus hashes."""
    manifesto = json.loads((pasta / 'manifesto.json').read_text(encoding='utf-8'))
    registros, vistos = [], set()
    for pagina in manifesto['paginas']:
        dados = (pasta / pagina['arquivo']).read_bytes()
        if hashlib.sha256(dados).hexdigest() != pagina['sha256']:
            raise ValueError('Resposta diferente do original: ' + pagina['arquivo'])
        payload = ler_resposta(dados.decode('utf-8'))
        for registro in analisar_resposta(payload, pagina['url'], pagina['coletado_em']):
            if registro['id_pncp'] not in vistos:
                vistos.add(registro['id_pncp'])
                registros.append(registro)
        if len(registros) >= limite:
            break
    return registros[:limite]


def exportar(registros, pasta):
    pasta.mkdir(parents=True, exist_ok=True)
    with (pasta / 'editais_extraidos.csv').open(
        'w', encoding='utf-8-sig', newline=''
    ) as arquivo:
        writer = csv.DictWriter(arquivo, fieldnames=CAMPOS, delimiter=';')
        writer.writeheader()
        writer.writerows(registros)
    (pasta / 'editais_extraidos.json').write_text(
        json.dumps(registros, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8',
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--limite', type=int, default=50, help='Quantidade de editais (mínimo 30).')
    parser.add_argument('--por-pagina', type=int, default=50, choices=[25, 50, 100])
    parser.add_argument('--offline', action='store_true', help='Reprocessar respostas PNCP salvas.')
    parser.add_argument('--saida', type=Path, default=RAIZ, help='Diretório dos arquivos gerados.')
    parser.add_argument(
        '--paginas', type=Path, default=RAIZ / 'paginas_pncp',
        help='Diretório das respostas JSON preservadas.',
    )
    args = parser.parse_args()
    if not 30 <= args.limite <= 500:
        parser.error('--limite deve estar entre 30 e 500.')
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    try:
        registros = (
            reproduzir(args.paginas, args.limite) if args.offline
            else coletar(args.limite, args.por_pagina, args.paginas)
        )
        if len(registros) < args.limite:
            raise ValueError(f'Só há {len(registros)} registros; solicitados {args.limite}.')
        exportar(registros, args.saida)
    except (OSError, ValueError, URLError, TimeoutError) as erro:
        logging.error('%s', erro)
        return 1
    logging.info('Concluído: %s editais únicos em %s', len(registros), args.saida.resolve())
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
