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

Cole um link do YouTube na barra do topo e pressione **Enter** (ou clique em
**Buscar**). Valem links completos (`youtube.com/watch?v=…`,
`music.youtube.com`, Shorts) e o link curto do próprio YouTube (`youtu.be/…`),
com ou sem `https://`. O aplicativo baixa
somente o áudio, na melhor qualidade disponível (sem reconversão), para a pasta
`músicas/` na raiz do projeto. Essa pasta não é rastreada pelo git. Todas as
músicas dela aparecem na lista da janela, que se atualiza automaticamente.

A barra continua livre durante um download: outros links entram numa fila de
downloads e são baixados um de cada vez, na ordem.

### Pesquisar no YouTube

Digite o nome da música (ou artista e música) na mesma barra e pressione
**Enter**. Qualquer texto que não seja um link abre a página de resultados, que
ocupa a janela principal como o player. Ela mostra os 10 primeiros vídeos do
YouTube, cada um com miniatura, título, canal e duração.

- **Adicionar** (ou ↑ ↓ para escolher e Enter) baixa o vídeo e volta às
  listas. A música entra em "A processar" como se o link tivesse sido colado.
- **▶** abre o vídeo no navegador, para conferir antes de escolher.
- O campo no topo da página permite pesquisar de novo; colar um link ali
  também baixa direto.
- **✕**, Esc ou Ctrl+W voltam às listas sem baixar nada.

Canais, playlists e transmissões ao vivo não aparecem nos resultados. A
pesquisa usa o próprio yt-dlp; nenhuma conta ou chave de API é necessária.

Se os downloads ou a pesquisa começarem a falhar, atualize o yt-dlp (`pip install -U yt-dlp`):
o YouTube muda com frequência.

### Excluir músicas

Selecione uma música em qualquer uma das listas e aperte **Delete**. Para
excluir várias de uma vez, selecione-as com Ctrl+clique ou Shift+clique. O app
pede confirmação e então apaga todos os arquivos da música:

- o áudio em `músicas/`;
- os vocais e o instrumental em `músicas/separadas/<nome>/`;
- a letra em `letras/<nome>.lrc` ou `.txt`;
- os metadados em `músicas/.metadados/<nome>.json`.

A exclusão é definitiva (não vai para a lixeira). Se a música estiver na fila
ou sendo processada, o processamento é cancelado; se estiver aberta no player,
ele é fechado.

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

As letras **não são baixadas automaticamente**. Quando você abre no player uma
música que ainda não tem letra, o app abre a busca de letra (ver
abaixo); o player só abre depois que você escolher uma, e não abre se você
cancelar. A letra escolhida é salva em `letras/` com o mesmo nome do arquivo de
áudio:

- `letras/<nome do áudio>.lrc` quando a letra é **sincronizada** (formato LRC,
  com o tempo de cada linha);
- `letras/<nome do áudio>.txt` quando é **sem sincronia**.

A sincronia é verificada no próprio texto: a maioria das linhas precisa começar
com um tempo `[mm:ss.xx]`, com pelo menos três tempos diferentes. Na lista
"Processadas" aparece a situação da letra de cada música. A pasta `letras/` não
é rastreada pelo git.

### Sincronização automática

As letras do LRCLIB costumam estar fora de sincronia com o áudio do YouTube
(introduções, cortes ou andamento diferentes da versão do álbum). Clique com o
botão direito numa música processada e escolha **Letra → Sincronizar
automaticamente com os vocais**. Usando o arquivo de vocais separados, o app:

1. mede os **ataques** da voz (instantes em que o volume sobe de repente, como
   no começo de cada verso) em quadros de 20 ms;
2. encontra o deslocamento (até ±90 s) e o andamento (±4%) em que o começo
   dos versos da letra mais coincide com esses ataques;
3. ajusta cada verso para o ataque nítido mais próximo (até ±0,3 s);
4. só aplica se o encaixe for **inequívoco** (pico de correlação destacado e
   sem outro parecido). Senão, avisa e não muda nada: provavelmente a letra é
   de outra versão da música. Se a letra já estava no lugar, avisa isso.

A letra original fica guardada (`letras/<nome>.original.lrc`) e pode ser
recuperada em **Letra → Restaurar letra original**. Se o player estiver aberto
com a música, a letra é atualizada na hora. Funciona só com letras
sincronizadas (`.lrc`): letras sem tempos precisariam de reconhecimento de fala.

### Busca de letra

A busca de letra ocupa a janela principal, como o player, e abre sozinha ao
tocar uma música sem letra. Para trocar uma letra
errada, clique com o botão direito numa música processada e escolha **Buscar
letra manualmente…**.

Ela já vem preenchida com o melhor palpite de artista e música (a partir
dos dados do vídeo guardados no download) e mostra os resultados do LRCLIB;
ajuste o texto e aperte Enter para buscar de novo. Os resultados mostram álbum,
duração (com a diferença para o áudio) e se a letra é sincronizada; as
sincronizadas de duração mais parecida aparecem primeiro. Selecione um
resultado para ver a letra e clique em **Usar esta letra** (ou **Usar e abrir o
player**, que já troca a busca pelo player). Nada é salvo sem essa escolha:
**✕**, **Cancelar**, Esc ou Ctrl+W voltam às listas sem mudar nada, com a
música selecionada.

### Player

Dê dois cliques (ou Enter) numa música da lista "Processadas" para abrir o
player. Ele ocupa a própria janela principal (no lugar das listas) e abre pronto
para tocar, mas só começa quando você der play. Para fechar, use o botão **✕**
no canto superior esquerdo, Esc ou Ctrl+W: as listas "A processar" e
"Processadas" voltam, com a música que estava tocando selecionada.

- **Letra sincronizada** destacada verso a verso: o verso atual fica sempre no
  meio da tela e a letra vai subindo, com animação, conforme os versos passam;
  clicar num verso pula para ele. Letras sem sincronia aparecem sem destaque.
- **Play/pause** (botão ou barra de espaço), barra de posição e setas ← → para
  voltar/avançar 5 s.
- **Tamanho da letra**: botões **A−** e **A+** ao lado do título (ou Ctrl − /
  Ctrl +; Ctrl 0 volta ao padrão), de 12 a 48 pt. O tamanho escolhido fica
  salvo e vale nas próximas vezes (em `~/.config/karaokay/karaoke.ini`).
- **Volume da voz e do instrumental separados**, de 0 a 100% (a voz começa em
  30%).
- **Sincronizar** manualmente: se a letra estiver adiantada ou atrasada, clique
  em "Sincronizar", toque a música e clique no primeiro verso (marcado com ▶)
  no instante em que ele começar a ser cantado. A letra inteira é deslocada e o
  ajuste fica salvo no próprio `.lrc` (tag padrão `[offset:ms]`), valendo nas
  próximas vezes. Esc ou "Cancelar" saem sem mudar nada.
- **Tela cheia**: botão **⛶**, ou F11; Esc sai (se estiver sincronizando, o
  primeiro Esc só cancela a sincronização; o Esc seguinte fecha o player). Ao
  sair — ou ao fechar o player em tela cheia — a janela volta ao tamanho que
  tinha.
- **Efeito de fundo** ("aurora"): manchas de luz suaves que se movem devagar e
  brilham um pouco mais quando a música fica mais intensa. É escuro e tem um
  véu na faixa do meio, onde fica o verso atual, para não atrapalhar a leitura.
  O botão **✦** liga e desliga (a escolha fica salva). A animação só roda com o
  player visível.
- Clicar em qualquer ponto de uma barra (posição, voz ou instrumental) leva
  direto àquele ponto, e dá para arrastar a partir dali.

Se houver música tocando, o app pede confirmação antes de fechar o player
(✕, Esc ou Ctrl+W) e antes de fechar a janela principal. Abrir outra música
substitui a que estava no player.

Os vocais e o instrumental são carregados na memória e misturados pelo próprio
app antes de ir para a placa de som, então os dois nunca se dessincronizam e a
mudança de volume vale na hora. A posição usada para destacar a letra é o tempo
que a placa de som já tocou de fato, o que desconta o buffer e a latência.

### Teclado

Tudo pode ser usado sem mouse; o elemento com foco fica destacado em violeta.

**Janela principal**

| Tecla | Ação |
|---|---|
| Tab / Shift+Tab | barra do topo → "A processar" → "Processadas" |
| Ctrl+L | vai para a barra do topo (com as listas visíveis) |
| Enter (na barra) | link: baixa; outro texto: pesquisa no YouTube |
| ↑ ↓ | escolhe a música na lista |
| Enter (em "Processadas") | abre no player |
| Delete | exclui (com confirmação); Shift/Ctrl + setas ou clique selecionam várias |
| Tecla de menu ou Shift+F10 | menu da música (abrir, buscar letra, excluir) |

**Player**

| Tecla | Ação |
|---|---|
| Tab / Shift+Tab | play → posição → Sincronizar → voz → instrumental → ⛶ → ✦ → A− → A+ → ✕ |
| Espaço | play/pause (num botão com foco, aciona o botão) |
| ← → | volta/avança 5 s (num slider com foco, mexe nele) |
| Enter | aciona o botão com foco |
| Na barra de posição: ← → / Page Up/Down / Home/End | ±5 s / ±30 s / início/fim |
| Nos volumes: ← → / Page Up/Down | ±5% / ±20% |
| Ctrl + / Ctrl − / Ctrl 0 | tamanho da letra |
| F11 | tela cheia; Esc sai |
| M | na sincronização, marca o primeiro verso (em vez de clicar) |
| Esc | cancela a sincronização; senão sai da tela cheia; senão fecha o player |
| Ctrl+W | fecha o player e volta às listas |

**Pesquisa no YouTube**

| Tecla | Ação |
|---|---|
| Tab / Shift+Tab | pesquisa → Buscar → resultados → ✕ |
| Enter (no campo) | pesquisa de novo (ou baixa, se for um link) |
| ↓ (no campo) | vai para os resultados |
| ↑ ↓ e Enter (nos resultados) | escolhe e adiciona |
| Esc / Ctrl+W | volta às listas |

**Busca de letra**

| Tecla | Ação |
|---|---|
| Tab / Shift+Tab | artista → música → Buscar → resultados → letra → Cancelar → Usar → ✕ |
| Enter (nos campos) | busca de novo |
| ↓ (nos campos) | vai para os resultados |
| ↑ ↓ e Enter (nos resultados) | escolhe e usa a letra |
| Esc / Ctrl+W | cancela e volta às listas |

### Modelo de separação

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
    song_delegate.py   cartões das músicas nas listas
    theme.py           tema escuro (cores, fonte e estilos)
    background.py      fundo animado do player
    splitter.py        divisória arrastável com alça visível
    player_window.py   player (ocupa a janela principal)
    lyrics_search_page.py    busca manual de letra (página da janela principal)
    youtube_results_page.py  resultados da pesquisa no YouTube (página)
  controllers/   ligam visões, modelos e serviços
    app_controller.py  download (e fila), pesquisa, processamento, exclusão e letras
    player_controller.py  player: áudio, letra e controles
    lyrics_search_controller.py  busca manual de letra
  services/      integrações externas, rodando em segundo plano
    downloader.py      yt-dlp (download do áudio)
    youtube_search.py  pesquisa no YouTube (yt-dlp) e miniaturas
    separator.py       audio-separator (BS-RoFormer)
    lyrics.py          busca de letras no LRCLIB (pela página de busca)
    auto_sync.py       sincronização automática da letra com os vocais
    stem_player.py     mistura e reprodução de vocais + instrumental
    files.py           remoção dos arquivos de uma música
  paths.py       pastas do projeto
  gc_guard.py    coleta de lixo só na thread principal (evita travamentos)
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
