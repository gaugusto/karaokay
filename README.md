# Karaokê

Aplicativo de karaokê para desktop, escrito em Python com interface em PySide6 (Qt 6).

## Requisitos

- Python 3.10+
- PySide6
- yt-dlp (download do áudio do YouTube)

## Como rodar

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m karaoke
```

(Durante o desenvolvimento, rode a partir da pasta `src/` ou instale o pacote com `pip install -e .`.)

## Uso

Cole um link do YouTube na barra do topo e pressione **Enter**. O aplicativo baixa
somente o áudio, na melhor qualidade disponível (sem reconversão), para a pasta
`músicas/` na raiz do projeto. Essa pasta não é rastreada pelo git. Todas as
músicas dela aparecem na lista da janela, que se atualiza automaticamente.

Se os downloads começarem a falhar, atualize o yt-dlp (`pip install -U yt-dlp`):
o YouTube muda com frequência.

## Estrutura

```
src/karaoke/     código do aplicativo
músicas/         áudios baixados (fora do git)
tests/           testes
```
