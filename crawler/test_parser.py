"""Testes locais de irregularidades reais que podem afetar um scraper HTML."""
import unittest
from crawler import analisar_html


class TestParser(unittest.TestCase):
    def parse(self, corpo):
        return analisar_html('<dl id="articles">' + corpo + '</dl>',
                             'https://arxiv.org/list/cs.AI/recent?skip=0&show=25',
                             '2026-10-27T12:00:00+00:00')

    def test_dd_ausente_nao_desloca_registro_seguinte(self):
        dados = self.parse('''<dt><a href="/abs/2610.00001">1</a></dt>
            <dt><a href="/abs/2610.00002">2</a></dt>
            <dd><div class="list-title">Title: Artigo correto</div></dd>''')
        self.assertEqual([(r['id_arxiv'], r['titulo']) for r in dados],
                         [('2610.00002', 'Artigo correto')])

    def test_classes_extras_tags_aninhadas_e_pdf_ausente(self):
        dados = self.parse('''<h3>Tue, 27 Oct 2026 (25 entries)</h3>
            <dt><a href="/abs/2610.00003">3</a></dt><dd>
            <div class="list-title mathjax classe-nova"><span>Title:</span> An <b>AI</b> study</div>
            <div class="list-subjects"><span>Subjects:</span>
            Artificial Intelligence (cs.AI); Machine Learning (cs.LG)</div></dd>''')
        r = dados[0]
        self.assertEqual(r['titulo'], 'An AI study')
        self.assertEqual(r['url_pdf'], '')
        self.assertEqual(r['data_anuncio'], '2026-10-27')
        self.assertEqual(r['assunto_principal'], 'Artificial Intelligence (cs.AI)')
        self.assertIn('Machine Learning', r['assuntos'])

    def test_fallback_titulo_sem_classe(self):
        dados = self.parse('''<dt><a href="https://arxiv.org/abs/2610.00004">4</a></dt>
            <dd><div><span>Title:</span> Título sem classe</div></dd>''')
        self.assertEqual(dados[0]['titulo'], 'Título sem classe')
        self.assertEqual(dados[0]['assuntos'], '')

    def test_data_muda_com_a_secao(self):
        dados = self.parse('''<h3>Tue, 27 Oct 2026</h3>
            <dt><a href="/abs/2610.00005">5</a></dt>
            <dd><div class="list-title">Title: Primeiro</div></dd>
            <h3>Mon, 26 Oct 2026</h3>
            <dt><a href="/abs/2610.00006">6</a></dt>
            <dd><div class="list-title">Title: Segundo</div></dd>''')
        self.assertEqual([r['data_anuncio'] for r in dados], ['2026-10-27', '2026-10-26'])

    def test_pagina_de_erro_nao_vira_dados(self):
        with self.assertRaises(ValueError):
            analisar_html('<html><h1>Access denied</h1></html>', 'https://arxiv.org', '')


if __name__ == '__main__':
    unittest.main()
