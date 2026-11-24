"""Provider-neutral USSD menu design; local mock output is not a live gateway."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class UssdRequest:
    session_id: str
    phone_number: str
    text: str


class UssdProvider(Protocol):
    name: str

    def respond(self, request: UssdRequest) -> str: ...


def render_menu(request: UssdRequest, *, language: str = "en") -> str:
    kiswahili = language == "sw"
    choices = request.text.split("*") if request.text else []
    if not choices or choices[-1] == "":
        body = "1 Hali ya hewa\n2 Bei za soko\n3 Ushauri wa mazao\n4 Upandaji\n5 Afisa wa kilimo\n6 Msaada" if kiswahili else "1 Weather\n2 Market prices\n3 Crop advice\n4 Planting information\n5 Agricultural officer\n6 Help"
        return "CON " + body
    selection = choices[-1]
    if selection == "1":
        body = "Hifadhi eneo la shamba au uliza afisa kupata utabiri." if kiswahili else "Save your farm location or ask an officer for a forecast."
    elif selection == "2":
        body = "Tuma SMS: PRICE MAIZE kupata bei iliyorekodiwa." if kiswahili else "Text PRICE MAIZE to request the latest recorded price."
    elif selection == "3":
        body = "Uliza afisa wa kilimo kwa ushauri unaofaa eneo lako." if kiswahili else "Ask your agricultural officer for advice suited to your area."
    elif selection == "4":
        body = "Muda wa kupanda hutegemea eneo na mvua. Uliza afisa." if kiswahili else "Planting timing depends on location and rainfall. Ask an officer."
    elif selection == "5":
        body = "Wasiliana na ofisi ya ugani ya kaunti yako." if kiswahili else "Contact your county agricultural extension office."
    else:
        body = "Tumia nambari 1 hadi 6." if kiswahili else "Choose a number from 1 to 6."
    return "END " + body


class MockUssdProvider:
    name = "mock_ussd"

    def respond(self, request: UssdRequest) -> str:
        # The simulator only renders the menu. It does not contact a carrier.
        return render_menu(request)
