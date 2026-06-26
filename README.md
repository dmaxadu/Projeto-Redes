# Manipulação de Rotas BGP como Instrumento de Controle Político — Myanmar 2021

Trabalho acadêmico produzido para a disciplina de Redes de Computadores (UFRJ).  
Analisa anomalias de roteamento BGP associadas ao golpe militar em Myanmar (fevereiro de 2021),
focando na dimensão **A8** (ataques cibernéticos e manipulação de rotas) em relação à questão
geopolítica **B9** (guerra civil em Myanmar).

**Autores:** Arlene Pelanda Juliene, Daniel Machado da Conceição, Leonardo de Melo Soares, Sylvio Heltt, Victor Pereira de Lima — Instituto de Ciência da Computação / UFRJ

---

## Estrutura do repositório

```
.
├── artigo/                        # Artigo em formato SBC LaTeX
│   ├── artigo.tex                 # Fonte principal
│   ├── artigo.pdf                 # PDF compilado
│   ├── referencias.bib            # Bibliografia
│   ├── sbc-template.sty           # Estilo SBC
│   └── sbc.bst                    # Estilo bibliográfico SBC
│
└── bgp-myanmar/
    ├── dados/                     # CSVs produzidos pelos scripts
    │   ├── m1_prefixos_visiveis.csv
    │   ├── m2_withdrawals_por_hora.csv   # gerado após coleta MRT completa
    │   ├── m3_aspath_medio.csv           # gerado após coleta MRT completa
    │   ├── m4_concentracao_upstreams.csv # gerado após coleta MRT completa
    │   ├── m5_hijack_104_244_42_0.csv
    │   ├── m6_cobertura_rpki.csv
    │   └── ioda_myanmar.csv
    ├── figuras/                   # Figuras geradas (PDF + PNG)
    │   ├── fig_withdrawals.pdf/png
    │   ├── fig_hijack.pdf/png
    │   └── fig_correlacao.pdf/png
    └── scripts/
        ├── 01_coletar_ripestat.py # M1, M6 — chamadas REST à RIPEstat API
        ├── 02_coletar_mrt.py      # M2, M3, M4, M5 — parse de MRT dumps
        ├── 03_coletar_ioda.py     # dados de tráfego (IODA/CAIDA)
        └── 04_gerar_graficos.py   # produz as 3 figuras do artigo
```

---

## Fenômenos investigados

1. **Withdrawals coordenados** — retiradas simultâneas de prefixos pelos ISPs AS9988 (MPT), AS136168 (Mytel), AS132748 (Ooredoo) e AS132167 (Atom) durante os apagões ordenados pela junta.
2. **Hijack BGP do Twitter** — em 5 de fevereiro de 2021 às 15h51 UTC, o AS136168 (Mytel) anunciou o prefixo `104.244.42.0/24` (pertencente ao Twitter, AS13414), mantendo o anúncio ilegítimo por mais de três horas.
3. **Correlação BGP × tráfego real** — comparação entre sinais de roteamento (RIPE RIS) e quedas de conectividade medidas pelo IODA/CAIDA e Cloudflare Radar.

---

## Métricas calculadas

| ID | Descrição | Fonte | Resultado |
|----|-----------|-------|-----------|
| M1 | Prefixos visíveis por ASN | RIPEstat API | AS9988: 41, AS136168: 5, AS132167: 35 |
| M2 | Withdrawals por janela de 1 hora | RouteViews MRT | CSV gerado |
| M3 | Comprimento médio do AS_PATH | RouteViews MRT | CSV gerado |
| M4 | Concentração nos top-5 upstreams | RouteViews MRT | CSV gerado |
| M5 | Detecção de mudança de origin AS (hijack) | RouteViews MRT | Hijack confirmado 15h51–18h58 UTC |
| M6 | Cobertura RPKI dos prefixos de Myanmar | RIPEstat API | AS9988: 92.7%, AS136168: 100%, AS132167: 100% |

---

## Como reproduzir

### Dependências

```bash
pip install mrtparse requests pandas matplotlib seaborn
```

### Passo a passo

```bash
# 1. Coleta via RIPEstat (M1 e M6) — rápido, apenas chamadas REST
python3 bgp-myanmar/scripts/01_coletar_ripestat.py

# 2. Coleta do hijack BGP de 5 fev 2021 (M5) — baixa ~200 MB de MRT dumps
python3 bgp-myanmar/scripts/02_coletar_mrt.py --modo m5

# 3. Coleta de withdrawals jan–abr 2021 (M2, M3, M4) — baixa ~2 GB, demorado
python3 bgp-myanmar/scripts/02_coletar_mrt.py --modo completo

# 4. Coleta de dados de tráfego (IODA/CAIDA)
python3 bgp-myanmar/scripts/03_coletar_ioda.py

# 5. Geração das 3 figuras
python3 bgp-myanmar/scripts/04_gerar_graficos.py

# 6. Compilação do artigo LaTeX
cd artigo && pdflatex artigo.tex && bibtex artigo && pdflatex artigo.tex && pdflatex artigo.tex
```

> **Nota:** se a API IODA retornar erro 404 (o endpoint público mudou após 2024), o script `03_coletar_ioda.py` usa automaticamente dados sintéticos calibrados com base nos eventos documentados em \[OONI 2021\] e \[NetBlocks 2021\].

### Prioridade mínima (ambiente limitado)

Se o tempo ou banda for restrito, execute apenas os passos 1, 2, 4 e 5. Isso produz as Figuras 2 e 3 com dados reais e a Figura 1 com dados sintéticos documentados.

---

## Fontes de dados

| Fonte | URL | Uso |
|-------|-----|-----|
| RIPEstat API | `https://stat.ripe.net/data/` | M1, M6 |
| RouteViews MRT | `http://archive.routeviews.org/bgpdata/` | M2, M3, M4, M5 |
| IODA / CAIDA | `https://api.ioda.inetintel.cc.gatech.edu/` | Figura 3 |
| OONI | `https://ooni.org/` | Contextualização |
| NetBlocks | `https://netblocks.org/` | Contextualização |

---

## Observação metodológica

BGP representa o **plano de controle** da Internet, não o plano de dados. Os AS_PATHs observados mostram por quais ASes um anúncio de rota se propagou — **não** por quais cabos ou roteadores físicos o tráfego efetivamente transitou. Todos os gráficos e análises adotam a formulação correta: *"os caminhos BGP observados incluem ASes associados ao país X"*, evitando afirmações sobre tráfego físico.
