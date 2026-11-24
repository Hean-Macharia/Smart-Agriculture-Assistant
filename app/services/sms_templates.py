"""Short bilingual SMS wording for ordinary-phone users."""

from app.models.notification import NotificationEvent

_TEMPLATES = {
    "en": {
        NotificationEvent.REGISTRATION.value: "Your ShambaLink account is ready. Reply STOP to stop SMS messages.",
        NotificationEvent.NEW_ORDER.value: "A ShambaLink order update is available. Sign in or contact your agricultural officer for help.",
        NotificationEvent.PAYMENT_CONFIRMATION.value: "A payment status update is available in ShambaLink. Contact support if you need help.",
        NotificationEvent.DELIVERY_UPDATE.value: "A delivery update is available in ShambaLink. Contact your buyer or seller if needed.",
        NotificationEvent.DISPUTE_UPDATE.value: "There is an update on your ShambaLink case. Contact your agricultural officer for help.",
        NotificationEvent.SELLER_PAYOUT.value: "A payout status update is available in ShambaLink. This message does not confirm a bank or M-Pesa transfer.",
        NotificationEvent.AGRICULTURAL_ADVISORY.value: "New crop guidance is available in ShambaLink. Ask your agricultural officer if you need help.",
        NotificationEvent.WEATHER_ALERT.value: "Weather information for your area is available. Follow local official weather alerts.",
        NotificationEvent.PLANTING_REMINDER.value: "Planting reminder: check local rainfall and ask your agricultural officer before planting.",
        NotificationEvent.CROP_MANAGEMENT_REMINDER.value: "Crop reminder: inspect your field and seek local extension advice if you see a problem.",
        NotificationEvent.MARKET_PRICE.value: "A market price update is available. Prices are observations and may change.",
        NotificationEvent.BUYER_ENQUIRY.value: "A buyer enquiry is available in your ShambaLink account.",
        NotificationEvent.DISEASE_WARNING.value: "Crop health warning: this is not a confirmed diagnosis. Ask an agricultural officer for advice.",
    },
    "sw": {
        NotificationEvent.REGISTRATION.value: "Akaunti yako ya ShambaLink iko tayari. Jibu STOP kusitisha SMS.",
        NotificationEvent.NEW_ORDER.value: "Kuna taarifa ya oda ya ShambaLink. Ingia au wasiliana na afisa wa kilimo.",
        NotificationEvent.PAYMENT_CONFIRMATION.value: "Kuna taarifa ya malipo kwenye ShambaLink. Wasiliana na usaidizi ukihitaji.",
        NotificationEvent.DELIVERY_UPDATE.value: "Kuna taarifa ya usafirishaji kwenye ShambaLink. Wasiliana na mnunuzi au mkulima.",
        NotificationEvent.DISPUTE_UPDATE.value: "Kuna taarifa mpya ya kesi yako ShambaLink. Wasiliana na afisa wa kilimo.",
        NotificationEvent.SELLER_PAYOUT.value: "Kuna taarifa ya malipo kwa mkulima ShambaLink. SMS hii haithibitishi kutumwa kwa fedha.",
        NotificationEvent.AGRICULTURAL_ADVISORY.value: "Ushauri mpya wa mazao unapatikana ShambaLink. Uliza afisa wa kilimo ukihitaji.",
        NotificationEvent.WEATHER_ALERT.value: "Taarifa ya hali ya hewa inapatikana. Fuata tahadhari rasmi za eneo lako.",
        NotificationEvent.PLANTING_REMINDER.value: "Kumbusho la kupanda: kagua mvua na uulize afisa wa kilimo kabla ya kupanda.",
        NotificationEvent.CROP_MANAGEMENT_REMINDER.value: "Kumbusho: kagua shamba lako na uulize afisa wa kilimo ukiona tatizo.",
        NotificationEvent.MARKET_PRICE.value: "Kuna taarifa ya bei ya soko. Bei hizi ni makadirio yaliyokusanywa na zinaweza kubadilika.",
        NotificationEvent.BUYER_ENQUIRY.value: "Kuna ujumbe wa mnunuzi kwenye akaunti yako ya ShambaLink.",
        NotificationEvent.DISEASE_WARNING.value: "Tahadhari ya afya ya zao: huu si utambuzi wa uhakika. Uliza afisa wa kilimo.",
    },
}


def render_event_message(event: str, language: str, fallback: str) -> str:
    return _TEMPLATES.get(language, _TEMPLATES["en"]).get(event, fallback)[:500]
