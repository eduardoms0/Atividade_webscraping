**Página alvo e estratégia do parser:** foi escolhida a **opção 3 (arXiv, artigos de Inteligência Artificial)**, em https://arxiv.org/list/cs.AI/recent. A paginação utiliza parâmetros GET: `skip` é o deslocamento inicial e `show` é a quantidade por página; nesta entrega são consultadas `?skip=0&show=25` e `?skip=25&show=25`. O BeautifulSoup usa `dl#articles` (com fallback para `find('dl')`), `find_all('dt')`, `a[href^="/abs/"]`, `.list-title`, `.list-subjects` e `.primary-subject`. Cada `dt` é associado ao próximo irmão `dt` ou `dd`, aceitando apenas `dd`, para que a ausência de uma tag não desloque os demais registros. Classes extras não impedem a seleção; um rótulo textual `Title:` serve de fallback quando a classe do título falta. Campos opcionais ausentes ficam vazios, títulos ausentes causam descarte com aviso e `get_text(' ', strip=True)` com normalização de espaços trata tags aninhadas.

# Construção de um crawler com parser

**Tema:** coleta e análise de metadados de artigos científicos de Inteligência Artificial.

O enunciado autoriza o arXiv como alternativa aos portais de editais. Por isso, os registros deste trabalho são **artigos científicos**, e os nomes `editais_extraidos.csv` e `editais_extraidos.json` seguem apenas a nomenclatura solicitada na atividade.

## Conteúdo da entrega

| Arquivo | Finalidade |
|---|---|
| `crawler.py` | Código completo e comentado: crawler, parser e exportação |
| `editais_extraidos.csv` | 50 registros reais e únicos, com cabeçalho |
| `editais_extraidos.json` | Os mesmos 50 registros, em JSON |
| `requirements.txt` | Dependência necessária para executar |
| `test_parser.py` | Testes de irregularidades do HTML |
| `paginas/pagina_000.html` e `pagina_001.html` | Respostas HTML preservadas para reprodução offline |
| `paginas/manifesto.json` | URLs consultadas, horários, quantidades e hashes SHA-256 |
| `paginas/robots.txt` | Regras consultadas durante a execução |

## Como executar

Requisitos: **Python 3.10 ou superior**, terminal e internet para uma nova coleta.
Extraia o ZIP e abra o terminal dentro da pasta `crawler_arxiv`.

```bash
python -m pip install -r requirements.txt
python crawler.py
```

No Windows, se o comando `python` não estiver disponível, utilize `py` no lugar dele.
Não é necessário instalar navegador, Selenium, banco de dados ou configurar credenciais.

Para uma **demonstração sem acesso à internet**, usando o mesmo parser e os HTMLs reais incluídos:

```bash
python crawler.py --offline --saida resultado_offline
```

O modo offline ainda precisa do BeautifulSoup instalado. Ele confere o hash dos HTMLs antes de processá-los e preserva os horários da coleta original. Não cria registros fictícios.

Para coletar outra quantidade ou salvar em outra pasta:

```bash
python crawler.py --limite 100 --por-pagina 25 --saida nova_coleta --paginas novas_paginas
```

`--limite` aceita de 30 a 500 registros. A seção `recent` muda ao longo do tempo; uma nova execução pode trazer outros artigos. A coleta falha com mensagem clara se a quantidade solicitada não for alcançada. O programa não substitui a falha por dados simulados.

## Funcionamento

1. Consulta `robots.txt` e verifica se a página alvo está permitida.
2. Faz requisições HTTP sequenciais com `urllib.request`, timeout de 30 segundos e identificação do crawler.
3. Respeita intervalo mínimo de 15 segundos ou o `Crawl-delay` informado pelo site, se maior. Esse intervalo também se aplica às retentativas; não há requisições paralelas.
4. Obtém os HTMLs das páginas `skip=0` e `skip=25`, com `show=25`.
5. Aplica o parser do BeautifulSoup e normaliza espaços, links relativos e campos ausentes.
6. Remove duplicatas pelo identificador arXiv e detecta páginas que não avançam.
7. Salva CSV, JSON e HTMLs com informações de proveniência.

Falhas transitórias de rede e códigos 429/500/502/503/504 recebem até três tentativas. Respostas 401/403 não são contornadas. A coleta tem um teto de 20 páginas. O programa não segue links de autores, não baixa PDFs nem os textos integrais dos artigos.

## Campos extraídos

| Campo | Significado |
|---|---|
| `id_arxiv` | Identificador único do artigo |
| `titulo` | Título bibliográfico |
| `data_anuncio` | Data da seção de anúncios na listagem, em ISO 8601 |
| `assunto_principal` | Classificação principal do artigo |
| `assuntos` | Classificações principal e secundárias, separadas por ponto e vírgula |
| `url_resumo` | Link da página pública do artigo |
| `url_pdf` | Link do PDF, sem baixar o documento |
| `pagina_origem` | URL paginada da qual o registro foi extraído |
| `coletado_em` | Horário da coleta em UTC, com fuso explícito |

A data do anúncio não deve ser interpretada como a data da primeira submissão do artigo.
Os autores não são extraídos para o conjunto estruturado; os HTMLs de reprodução conservam a página pública original.

O CSV usa **UTF-8 com BOM** e **ponto e vírgula** como delimitador para facilitar a abertura no Excel em português. Caso as colunas não sejam separadas automaticamente, use **Dados → De Texto/CSV**, selecione UTF-8 e delimitador ponto e vírgula.

## Verificação

```bash
python -m unittest -v test_parser.py
python crawler.py --offline --saida resultado_offline
```

Os testes verificam ausência de `dd`, classes adicionais, tags aninhadas, PDF ausente, título sem classe, mudança de data entre seções e página de erro. Os arquivos CSV e JSON podem ser comparados com os produzidos offline: o conteúdo deve ser idêntico.

## Fontes e limites

- Listagem pública: https://arxiv.org/list/cs.AI/recent
- Regras de acesso verificadas na coleta: https://arxiv.org/robots.txt
- Biblioteca utilizada: https://www.crummy.com/software/BeautifulSoup/bs4/doc/

A atividade foi implementada sobre HTML público, sem autenticação ou evasão de bloqueios. Alterações estruturais no site podem exigir novos seletores. A listagem varia diariamente; os HTMLs preservados e o manifesto documentam os dados desta entrega.
