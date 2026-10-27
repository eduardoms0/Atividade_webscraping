# Coleta de editais públicos no PNCP

**Página-alvo:** consulta oficial de contratações publicadas no [Portal Nacional de Contratações Públicas (PNCP)](https://pncp.gov.br/api/consulta/v1/contratacoes/publicacao). A coleta filtra a modalidade de código `6` (Pregão - Eletrônico) e os últimos 30 dias. A paginação da API começa em `pagina=1` e avança pelo parâmetro `tamanhoPagina` (50 por padrão). A resposta da consulta é JSON, não HTML: por isso, os registros são encontrados pelas chaves estáveis da API, sem seletores CSS. O código trata campos opcionais ausentes com acessos defensivos a dicionários aninhados. Para respostas de erro que venham em HTML, usa BeautifulSoup com `get_text(' ', strip=True)` para extrair a mensagem mesmo com tags aninhadas; classes dinâmicas não são necessárias na extração dos editais.

## Arquivos

| Arquivo | Finalidade |
|---|---|
| `crawler.py` | Cliente da API, normalização dos editais e exportação |
| `editais_extraidos.csv` | Editais coletados em CSV, separados por ponto e vírgula |
| `editais_extraidos.json` | Os mesmos registros em JSON |
| `requirements.txt` | Dependência BeautifulSoup para identificar mensagens em respostas HTML de erro |
| `test_parser.py` | Testes de campos ausentes, dados aninhados e respostas HTML de erro |
| `paginas_pncp/` | Respostas JSON da API, manifesto e hashes para reprodução offline |

## Executar

Requisitos: Python 3.10 ou superior e internet para uma nova coleta.

```powershell
py -m pip install -r requirements.txt
py crawler.py
```

O comando coleta 50 editais de pregão eletrônico publicados no PNCP nos últimos 30 dias e salva CSV e JSON na pasta `crawler`.

Para executar os testes:

```powershell
py -m unittest -v test_parser.py
```

Depois de uma coleta online, a reprodução offline reprocessa os JSONs salvos e confere seus hashes:

```powershell
py crawler.py --offline --saida resultado_offline
```

## Opções

```powershell
py crawler.py --limite 100 --por-pagina 50 --saida minha_coleta
```

- `--limite`: quantidade de editais, de 30 a 500.
- `--por-pagina`: tamanho da página da API: 25, 50 ou 100.
- `--saida`: diretório dos arquivos CSV e JSON.
- `--paginas`: diretório dos JSONs preservados e do manifesto.
- `--offline`: reprocessa os JSONs de uma coleta já salva, sem consultar o PNCP.

Se não houver editais suficientes no período, o crawler informa o erro em vez de gerar registros fictícios.

## Campos extraídos

O CSV e o JSON contêm identificador PNCP, número da compra, processo, objeto, órgão, CNPJ, UF, município, modalidade, situação, datas de publicação e de propostas, valor estimado, URL do edital, URL de origem da página da API e horário da coleta em UTC.

O crawler usa a API pública do PNCP e não baixa anexos ou documentos dos editais.
