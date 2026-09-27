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

Assim que um download termina, a música entra numa fila e é separada em vocais e
instrumental com o BS-RoFormer (`model_bs_roformer_ep_317_sdr_12.9755.ckpt`), via
[audio-separator](https://github.com/nomadkaraoke/python-audio-separator). O
resultado fica em `músicas/separadas/<nome da música>/vocais.flac` e
`instrumental.flac`. Antes de separar, o áudio é decodificado com o ffmpeg,
então qualquer formato funciona. Na lista, músicas ainda não separadas aparecem em cinza.

Na primeira separação o modelo (algumas centenas de MB) é baixado para `modelos/`,
também fora do git. Se o app for fechado no meio de uma separação, ela é refeita
na próxima vez que ele abrir.

## Estrutura (MVC)

```
src/karaoke/
  models/        dados e estado, sem interface
    song.py            Song e SongState (não separada, na fila, separando…)
    library_model.py   MusicLibraryModel (QAbstractListModel das músicas)
  views/         widgets: só exibem dados e emitem sinais
    main_window.py     janela principal
    song_delegate.py   desenho de cada música na lista
  controllers/   ligam visões, modelos e serviços
    app_controller.py  fluxo de download e separação
  services/      integrações externas, rodando em segundo plano
    downloader.py      yt-dlp
    separator.py       audio-separator (BS-RoFormer)
  paths.py       pastas do projeto
tests/           testes (pytest)
músicas/         áudios baixados (fora do git)
  separadas/     vocais e instrumental de cada música
modelos/         modelos de separação (fora do git)
```

## Testes

```bash
uv pip install -e ".[dev]"
.venv/bin/pytest
```
