from pydantic import BaseModel


class ApiV1Prefix(BaseModel):
    prefix: str = "/v1"
    users: str = "/users"
    sync: str = "/sync"
    me: str = "/me"
    profile: str = "/profile"
    settings: str = "/settings"
    library: str = "/library"
    decks: str = "/decks"
    cards: str = "/cards"
    share: str = "/share"
    study: str = "/study"
    sessions: str = "/sessions"
    active: str = "/active"
    reviews: str = "/reviews"
