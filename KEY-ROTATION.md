# Assinatura da base e rotação de chave

## Formato publicado (GitHub Release `latest`)

| Arquivo | Conteúdo |
|---|---|
| `tolls_br.bin.gz` | A base (ver `FORMAT.md`). |
| `manifest.json` | JSON canônico (chaves ordenadas, sem espaços, UTF-8, `\n` final). |
| `manifest.sig` | Assinatura Ed25519 **crua de 64 bytes** sobre os bytes exatos de `manifest.json`. |

Campos de `manifest.json`: `manifestFormat` (1), `version` (inteiro crescente = `datasetVersion` do cabeçalho),
`buildDate` (`AAAA-MM-DD`), `file` (`tolls_br.bin.gz`), `size` (bytes), `sha256` (hex minúsculo),
`minAppVersion` (inteiro). Coerente com o plano §5.3: o app baixa manifest+sig, verifica a assinatura com a(s) chave(s)
pública(s) embutida(s), compara `version`, baixa o arquivo e confere `size` e `sha256`. Chave pública: 32 bytes crus,
distribuída em base64 (`public-keys/*.pub` neste repositório guarda o PEM; `sign_release.py pubkey` imprime o base64).

## Ferramentas

`sign_release.py` (stdlib + CLI `openssl` >= 1.1.1; sem dependência Python extra): `manifest`, `sign`, `verify`, `pubkey`.
A chave privada vem **somente** do segredo/variável `DRIVELENS_DATA_SIGNING_KEY` e é passada ao openssl por stdin
(nunca gravada em disco). Nenhuma chave privada pode ser commitada (`*.pem`/`*.key` estão no `.gitignore`).

## Gerar a chave (uma vez, na máquina do humano, fora do repositório)

```bash
openssl genpkey -algorithm ed25519 -out ~/drivelens-data-signing.pem   # guardar em cofre de senhas
DRIVELENS_DATA_SIGNING_KEY="$(cat ~/drivelens-data-signing.pem)" python3 -I sign_release.py pubkey   # base64 para o app
openssl pkey -in ~/drivelens-data-signing.pem -pubout -out public-keys/current.pub                    # commitar só o .pub
```
Cadastrar o PEM como segredo do repositório (Settings > Secrets and variables > Actions > `DRIVELENS_DATA_SIGNING_KEY`).

## Rotação (o app aceita uma LISTA de chaves públicas, plano §7)

Planejada (a cada 12 meses ou por troca de responsável):
1. Gerar a nova chave (acima) e obter o base64 da nova pública.
2. **Release do app N** com a lista `[chave antiga, chave nova]` embutida; esperar a adoção (>= 90% dos usuários ativos).
3. Trocar o segredo `DRIVELENS_DATA_SIGNING_KEY` pela nova privada e `public-keys/current.pub` pela nova pública; disparar a release.
4. **Release do app N+1** removendo a chave antiga da lista. Destruir a privada antiga.

Comprometimento (vazamento suspeito): 1) revogar/trocar o segredo imediatamente e suspender a Action;
2) gerar nova chave; 3) release urgente do app com a lista contendo SÓ a nova chave (apps antigos deixam de aceitar
atualizações, mas continuam com a base embutida, que é o comportamento seguro); 4) republicar a base assinada com a nova chave;
5) registrar o incidente. Releases assinadas com a chave comprometida devem ser apagadas.

Regras: uma base sintética nunca é publicada (`--require-publishable` em validate e build); a versão só aumenta.
