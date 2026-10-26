# tools/drivelens-data/coverage

Levantamento de cobertura de praças de pedágio (T-TOL-001). Python 3.9+, só biblioteca padrão. Só trata dados públicos de praças; nenhum dado do usuário entra aqui (Princípio II).

## Testes (offline, fixtures sintéticas)

```bash
python3 -I tools/drivelens-data/coverage/tests/test_coverage_tool.py
```

## Execução real (ação humana, precisa de rede)

```bash
WORK=$(mktemp -d)   # diretório novo e vazio
python3 -I tools/drivelens-data/coverage/fetch_sources.py --work-dir "$WORK" --antt-url "<URL do CSV 'Praças de pedágio' da ANTT>"
# ARTESP: salvar a lista de praças de SP em $WORK/artesp.csv (cabeçalho: nome,uf,lat,lon)
cd tools/drivelens-data/coverage && python3 -I report.py --antt "$WORK/antt.csv" --osm "$WORK/osm.json" \
  --artesp "$WORK/artesp.csv" --run-date $(date +%F) --out "$WORK/relatorio.md"
```

Colar o conteúdo de `relatorio.md` na seção "RESULTADO" de `docs/research/toll-coverage.md`.

## Fontes e licenças

| Fonte | Uso | Licença / atribuição |
|---|---|---|
| ANTT, dados abertos, conjunto "Praças de pedágio" (portal dados.gov.br / dados.antt.gov.br; a URL do recurso CSV muda, por isso é argumento) | praças federais, UF, rodovia, km, coordenadas | Licença aberta do portal (conferir na página do conjunto e citar a ANTT como fonte) |
| OpenStreetMap via Overpass (`barrier=toll_booth`, `highway=toll_gantry`) | pontos de cobrança | ODbL 1.0, (c) colaboradores do OpenStreetMap; atribuição obrigatória no app |
| ARTESP, lista de praças de SP | referência de SP | Publicação oficial; sem URL estável assumida, baixar à mão e registrar a data |

Cabeçalhos do CSV da ANTT são lidos de forma tolerante (`praça/nome`, `uf`, `rodovia`, `km`, `latitude`, `longitude`; separador `;` ou `,`). Se o arquivo real usar outros nomes, ajustar `ALIASES` em `coverage_tool.py`.

## Método

Cruzamento um-para-um por proximidade (haversine, raio padrão 1500 m, pares mais próximos primeiro). Cobertura por UF = cruzadas / praças ANTT. Pontos OSM sem UF herdam a da praça ANTT cruzada, senão vão para `??`. Praças sem coordenadas contam como "Sem coordenadas" e nunca cruzam.
