# Karaokê

Aplicativo de karaokê para desktop, escrito em Python com interface em PySide6 (Qt 6).

## Requisitos

- Python 3.10 a 3.13 (o 3.14 ainda não é suportado pelo audio-separator)
- PySide6
- yt-dlp (download do áudio do YouTube)
- audio-separator com o modelo BS-RoFormer (separação de vocais)
- ffmpeg instalado no sistema (Arch: `sudo pacman -S ffmpeg`)
- Placa NVIDIA recomendada; na CPU a separação é bem mais lenta

## Como rodar

Com o [uv](https://docs.astral.sh/uv/) (`sudo pacman -S uv`), que baixa o Python
3.13 sozinho se o sistema tiver outra versão:

```bash
uv venv                        # usa o Python do arquivo .python-version (3.13)
uv pip install -e ".[gpu]"     # sem NVIDIA: ".[cpu]"
.venv/bin/python -m karaoke
```

Use sempre a instalação editável (`-e`): assim as pastas `músicas/` e `modelos/`
ficam na raiz do projeto.

## Uso

Cole um link do YouTube na barra do topo e pressione **Enter**. O aplicativo baixa
somente o áudio, na melhor qualidade disponível (sem reconversão), para a pasta
`músicas/` na raiz do projeto. Essa pasta não é rastreada pelo git. Todas as
músicas dela aparecem na lista da janela, que se atualiza automaticamente.

Se os downloads começarem a falhar, atualize o yt-dlp (`pip install -U yt-dlp`):
o YouTube muda com frequência.

### Separação de vocais

A janela tem duas listas, uma sobre a outra:

- **A processar** (em cima): músicas que ainda precisam ter os vocais separados, na ordem
  de chegada. Elas são processadas por uma fila, uma de cada vez, nunca em
  paralelo. A que está sendo processada aparece em primeiro, em negrito, com a
  porcentagem do processamento.
- **Processadas** (embaixo): músicas já separadas, em ordem alfabética.

Assim que uma música termina de ser processada, ela sai de "A processar" e vai
para "Processadas". A separação usa o BS-RoFormer
(`model_bs_roformer_ep_317_sdr_12.9755.ckpt`), via
[audio-separator](https://github.com/nomadkaraoke/python-audio-separator), e o
resultado fica em `músicas/separadas/<nome da música>/vocais.flac` e
`instrumental.flac`. Antes de separar, o áudio é decodificado com o ffmpeg,
então qualquer formato funciona. Músicas colocadas à mão na pasta `músicas/`
também entram na fila. Se o processamento de uma música falhar, ela fica no fim
de "A processar" e é tentada de novo na próxima vez que o app abrir.

### Letras

Depois de processada, a música ganha a letra do [LRCLIB](https://lrclib.net),
salva em `letras/` com o mesmo nome do arquivo de áudio:

- `letras/<nome do áudio>.lrc` quando a letra é **sincronizada** (formato LRC,
  com o tempo de cada linha);
- `letras/<nome do áudio>.txt` quando o LRCLIB só tem a letra **sem sincronia**.

A busca usa os dados do vídeo guardados no download (título, artista, canal e
duração, em `músicas/.metadados/`) e a duração real do áudio: primeiro tenta a
correspondência exata (`/api/get`, ±2 s) e depois a busca livre (`/api/search`),
preferindo letras sincronizadas e descartando versões com duração muito
diferente. A sincronia é verificada no próprio texto: a maioria das linhas
precisa começar com um tempo `[mm:ss.xx]`, com pelo menos três tempos
diferentes. Na lista "Processadas" aparece a situação da letra de cada música
(sincronizada, sem sincronia, sem letra…); as que não têm letra sincronizada
ficam em cinza. A pasta `letras/` não é rastreada pelo git.

### Player

Dê dois cliques (ou Enter) numa música da lista "Processadas" para abrir o
player:

- **Letra sincronizada** destacada verso a verso, sempre centralizada; clicar
  num verso pula para ele. Letras sem sincronia aparecem inteiras, sem destaque.
- **Play/pause** (botão ou barra de espaço), barra de posição e setas ← → para
  voltar/avançar 5 s.
- **Volume da voz e do instrumental separados**, de 0 a 100%.

Os vocais e o instrumental são carregados na memória e misturados pelo próprio
app antes de ir para a placa de som, então os dois nunca se dessincronizam e a
mudança de volume vale na hora. A posição usada para destacar a letra é o tempo
que a placa de som já tocou de fato, o que desconta o buffer e a latência.

Na primeira separação o modelo (algumas centenas de MB) é baixado para `modelos/`,
também fora do git. Se o app for fechado no meio de uma separação, ela é refeita
na próxima vez que ele abrir.

## Estrutura (MVC)

```
src/karaoke/
  models/        dados e estado, sem interface
    song.py            Song e SongState (não separada, na fila, separando…)
    library_model.py   MusicLibraryModel (QAbstractListModel das músicas)
    song_lists.py      listas filtradas: a processar e processadas
    lyrics.py          estado da letra e verificação de sincronia
    lrc.py             leitura de letras LRC (verso e tempo)
  views/         widgets: só exibem dados e emitem sinais
    main_window.py     janela principal
    song_delegate.py   desenho das músicas nas listas
    player_window.py   janela do player
  controllers/   ligam visões, modelos e serviços
    app_controller.py  download, fila de processamento e letras
    player_controller.py  player: áudio, letra e controles
  services/      integrações externas, rodando em segundo plano
    downloader.py      yt-dlp
    separator.py       audio-separator (BS-RoFormer)
    lyrics.py          busca de letras no LRCLIB
    stem_player.py     mistura e reprodução de vocais + instrumental
  paths.py       pastas do projeto
tests/           testes (pytest)
músicas/         áudios baixados (fora do git)
  separadas/     vocais e instrumental de cada música
letras/          letras .lrc/.txt (fora do git)
modelos/         modelos de separação (fora do git)
```

## Testes

```bash
uv pip install -e ".[dev]"
.venv/bin/pytest
```
