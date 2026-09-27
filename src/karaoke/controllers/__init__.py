"""Controladores: ligam as visões aos modelos e serviços."""

from karaoke.controllers.app_controller import AppController
from karaoke.controllers.lyrics_search_controller import LyricsSearchController
from karaoke.controllers.player_controller import PlayerController

__all__ = ["AppController", "LyricsSearchController", "PlayerController"]
