import unittest

from crawler import analisar_resposta, ler_resposta


class TestParserPNCP(unittest.TestCase):
    def test_normaliza_edital_e_link(self):
        payload = {'data': [{
            'numeroControlePNCP': '12345678000199-1-000001/2026',
            'numeroCompra': '1/2026',
            'processo': '123/2026',
            'objetoCompra': 'Aquisição de materiais.',
            'anoCompra': 2026,
            'sequencialCompra': 1,
            'dataPublicacaoPncp': '2026-10-01T10:00:00',
            'valorTotalEstimado': 25000.0,
            'modalidadeNome': 'Pregão - Eletrônico',
            'situacaoCompraNome': 'Divulgada no PNCP',
            'orgaoEntidade': {'cnpj': '12345678000199', 'razaoSocial': 'Órgão público'},
            'unidadeOrgao': {'ufSigla': 'SP', 'municipioNome': 'São Paulo'},
        }]}
        registros = analisar_resposta(payload, 'https://pncp.gov.br/api?page=1', 'coleta')
        self.assertEqual(len(registros), 1)
        registro = registros[0]
        self.assertEqual(registro['objeto'], 'Aquisição de materiais.')
        self.assertEqual(registro['orgao'], 'Órgão público')
        self.assertEqual(registro['url_edital'],
                         'https://pncp.gov.br/app/editais/12345678000199/2026/1')

    def test_campos_opcionais_e_dados_aninhados_ausentes(self):
        registros = analisar_resposta({
            'data': [{
                'numeroControlePNCP': 'id-2',
                'objetoCompra': 'Serviço de manutenção',
                'orgaoEntidade': None,
                'unidadeOrgao': None,
            }],
        }, 'url', 'coleta')
        self.assertEqual(registros[0]['orgao'], '')
        self.assertEqual(registros[0]['uf'], '')
        self.assertEqual(registros[0]['url_edital'], '')
        self.assertIsNone(registros[0]['valor_estimado'])

    def test_descarta_registro_sem_identificador_ou_objeto(self):
        registros = analisar_resposta({'data': [
            {'numeroControlePNCP': 'id-sem-objeto'},
            {'objetoCompra': 'objeto-sem-id'},
        ]}, 'url', 'coleta')
        self.assertEqual(registros, [])

    def test_resposta_html_de_erro_e_convertida_em_mensagem_legivel(self):
        with self.assertRaisesRegex(ValueError, 'Access denied'):
            ler_resposta('<html><body><h1>Access <b>denied</b></h1></body></html>')

    def test_json_sem_lista_de_dados_e_rejeitado(self):
        with self.assertRaisesRegex(ValueError, 'campo data ausente'):
            analisar_resposta({'mensagem': 'erro'}, 'url', 'coleta')


if __name__ == '__main__':
    unittest.main()
