# Formato de `tolls_br.bin.gz`

Ver o docstring de `build.py` (fonte da verdade do layout, big-endian, versão de formato 1).
O bit 0 de `flags` marca base sintética/vazia: **não publicável**. O app (T-TOL-005/011) DEVE tratar esse bit como "sem dados" e nunca exibir seus valores como reais.
