from dataclasses import dataclass, field


@dataclass
class Song:
    platform: str
    title: str
    artist: str
    cover_url: str = ""
    audio_url: str = ""
    song_id: str = ""
    duration: int = 0
    extra: dict = field(default_factory=dict)

    @property
    def display_name(self) -> str:
        return f"{self.title} - {self.artist}"
