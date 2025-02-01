from typing import Text, List, Any, Dict, Optional
from rasa_sdk import Tracker, FormValidationAction, Action
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.types import DomainDict
from rasa_sdk.events import SlotSet, AllSlotsReset, ActiveLoop

VALID_CITIES = ["Dhaka", "New York", "London", "Tokyo", "Dubai", "Mumbai", "Paris", "Khulna", "Rajshahi"]

def normalize_message(message: Text) -> Text:
    """Normalize user message by removing extra whitespace and line breaks."""
    return " ".join(message.split())

def parse_cities_from_message(message: Text) -> List[Text]:
    """Find all valid cities mentioned in the user message in order."""
    msg_lower = message.lower()
    mentioned = []
    for city in VALID_CITIES:
        if city.lower() in msg_lower:
            mentioned.append(city)
    # Sort by first occurrence in the message
    mentioned = sorted(mentioned, key=lambda c: msg_lower.index(c.lower()))
    return mentioned

def infer_source_destination(message: Text, already_set_source: Optional[Text], already_set_destination: Optional[Text]) -> (Optional[Text], Optional[Text]):
    """Try to infer source and destination from the message using heuristics."""
    # Normalize message
    message = normalize_message(message)
    msg_lower = message.lower()
    mentioned = parse_cities_from_message(message)

    # If no cities found
    if not mentioned:
        return None, None

    # If source is already set and we only need destination
    if already_set_source and not already_set_destination:
        possible_dests = [c for c in mentioned if c.lower() != already_set_source.lower()]
        if len(possible_dests) == 1:
            return already_set_source, possible_dests[0]
        elif len(possible_dests) > 1:
            # Try to find a city after "to"
            to_idx = msg_lower.find("to ")
            if to_idx != -1:
                for c in possible_dests:
                    if msg_lower.find(c.lower()) > to_idx:
                        return already_set_source, c
            # If we can't decide, pick the first different city
            return already_set_source, possible_dests[0]
        else:
            return already_set_source, None

    # If destination is already set and we only need source
    if already_set_destination and not already_set_source:
        possible_sources = [c for c in mentioned if c.lower() != already_set_destination.lower()]
        if len(possible_sources) == 1:
            return possible_sources[0], already_set_destination
        elif len(possible_sources) > 1:
            from_idx = msg_lower.find("from ")
            if from_idx != -1:
                for c in possible_sources:
                    if msg_lower.find(c.lower()) > from_idx:
                        return c, already_set_destination
            return possible_sources[0], already_set_destination
        else:
            return None, already_set_destination

    # If we have neither source nor destination:
    from_idx = msg_lower.find("from ")
    to_idx = msg_lower.find("to ")

    if from_idx != -1 and to_idx != -1:
        city_after_from = None
        city_after_to = None
        for c in mentioned:
            cidx = msg_lower.find(c.lower())
            if cidx > from_idx and (city_after_from is None or cidx < msg_lower.find(city_after_from.lower())):
                city_after_from = c
            if cidx > to_idx and (city_after_to is None or cidx < msg_lower.find(city_after_to.lower())):
                city_after_to = c
        if city_after_from and city_after_to and city_after_from.lower() != city_after_to.lower():
            return city_after_from, city_after_to

    # If no clear 'from'/'to' pattern, fallback to order
    if len(mentioned) >= 2:
        return mentioned[0], mentioned[1]
    elif len(mentioned) == 1:
        # Only one city found
        return mentioned[0], None

    return None, None

class ActionAskSource(Action):
    def name(self) -> Text:
        return "action_ask_source"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        dispatcher.utter_message(text=f"Which city would you like to fly from? Available cities: {', '.join(VALID_CITIES)}")
        return []

class ActionAskDestination(Action):
    def name(self) -> Text:
        return "action_ask_destination"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        source = tracker.get_slot("source")
        available_destinations = [c for c in VALID_CITIES if not source or c.lower() != source.lower()]
        dispatcher.utter_message(text=f"Which city would you like to fly to? Available cities: {', '.join(available_destinations)}")
        return []

class ValidateFlightBookingForm(FormValidationAction):
    def name(self) -> Text:
        return "validate_flight_booking_form"

    async def required_slots(
        self,
        domain_slots: List[Text],
        dispatcher: "CollectingDispatcher",
        tracker: "Tracker",
        domain: "DomainDict",
    ) -> List[Text]:
        return ["source", "destination"]

    def validate_source(
        self,
        slot_value: Any,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict,
    ) -> Dict[Text, Any]:
        city = (slot_value.strip().title() if slot_value else "").strip()
        
        if city not in VALID_CITIES:
            # Fallback parsing
            user_msg = tracker.latest_message.get("text", "")
            user_msg = normalize_message(user_msg)
            current_source = tracker.get_slot("source")
            current_destination = tracker.get_slot("destination")
            inferred_source, inferred_destination = infer_source_destination(user_msg, current_source, current_destination)

            if inferred_source and inferred_source in VALID_CITIES:
                if inferred_destination and inferred_destination in VALID_CITIES and inferred_destination.lower() != inferred_source.lower():
                    return {"source": inferred_source, "destination": inferred_destination}
                else:
                    return {"source": inferred_source}
            else:
                dispatcher.utter_message(text=f"Sorry, '{city}' is not a valid city. Please choose from: {', '.join(VALID_CITIES)}")
                dispatcher.utter_message(text="Please select a valid source city.")
                return {"source": None}
        else:
            # Valid source
            return {"source": city}

    def validate_destination(
        self,
        slot_value: Any,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict,
    ) -> Dict[Text, Any]:
        city = (slot_value.strip().title() if slot_value else "").strip()
        source = tracker.get_slot("source")
        available_destinations = [c for c in VALID_CITIES if not source or c.lower() != source.lower()]

        if city not in available_destinations:
            # Fallback parsing
            user_msg = tracker.latest_message.get("text", "")
            user_msg = normalize_message(user_msg)
            current_source = tracker.get_slot("source")
            current_destination = tracker.get_slot("destination")
            inferred_source, inferred_destination = infer_source_destination(user_msg, current_source, current_destination)

            if current_source and not current_destination:
                # Only need destination
                if inferred_destination and inferred_destination in available_destinations:
                    return {"destination": inferred_destination}

            if not current_source and not current_destination:
                # If both found from fallback
                if (inferred_source and inferred_destination and
                    inferred_source in VALID_CITIES and 
                    inferred_destination in VALID_CITIES and 
                    inferred_source.lower() != inferred_destination.lower()):
                    return {"source": inferred_source, "destination": inferred_destination}
            
            dispatcher.utter_message(text=f"Sorry, '{city}' is not a valid destination. Please choose from: {', '.join(available_destinations)}")
            dispatcher.utter_message(text="Please select a valid destination city.")
            return {"destination": None}

        if source and city.lower() == source.lower():
            dispatcher.utter_message(text="Source and destination cannot be the same city. Please choose a different destination.")
            return {"destination": None}

        return {"destination": city}

class ActionSubmitFlight(Action):
    def name(self) -> Text:
        return "action_submit_flight"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        source = tracker.get_slot("source")
        destination = tracker.get_slot("destination")
        latest_intent = tracker.get_intent_of_latest_message()

        # Validate once more
        if source not in VALID_CITIES or destination not in VALID_CITIES:
            dispatcher.utter_message(text="Sorry, invalid city detected. Let's start over.")
            return [AllSlotsReset(), ActiveLoop(None)]
        
        if latest_intent == "affirm":
            dispatcher.utter_message(
                text=f"Your flight from {source} to {destination} has been booked successfully!"
            )
            return [AllSlotsReset(), ActiveLoop(None)]
        elif latest_intent == "deny":
            dispatcher.utter_message(text="Booking cancelled.")
            return [AllSlotsReset(), ActiveLoop(None)]
        else:
            dispatcher.utter_message(
                text=f"I've found flights from {source} to {destination}. Would you like to proceed with booking? (Yes/No)"
            )
            return []

class ActionCheckFlightFormStart(Action):
    def name(self) -> Text:
        return "action_check_flight_form_start"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        # Before starting the form, try to infer source and destination from the user's last message
        user_msg = tracker.latest_message.get("text", "")
        user_msg = normalize_message(user_msg)
        current_source = tracker.get_slot("source")
        current_destination = tracker.get_slot("destination")
        inferred_source, inferred_destination = infer_source_destination(user_msg, current_source, current_destination)

        events = []
        if inferred_source and inferred_source in VALID_CITIES:
            events.append(SlotSet("source", inferred_source))
        if inferred_destination and inferred_destination in VALID_CITIES and (not inferred_source or inferred_destination.lower() != inferred_source.lower()):
            events.append(SlotSet("destination", inferred_destination))

        # Start the flight booking form
        events.append(ActiveLoop("flight_booking_form"))
        return events

class ActionResetFlightForm(Action):
    def name(self) -> Text:
        return "action_reset_flight_form"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        return [AllSlotsReset(), ActiveLoop(None)]

from typing import Any, Text, Dict, List
from rasa_sdk import Action, Tracker
from rasa_sdk.events import SessionStarted, ActionExecuted


class ActionSessionStart(Action):
    def name(self) -> Text:
        return "action_session_start"

    async def run(
      self, dispatcher, tracker: Tracker, domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:
        metadata = tracker.get_slot("session_started_metadata")

        # Do something with the metadata
        if metadata is not None:
            print(metadata)
        dispatcher.utter_message(text="Session started.")

        # the session should begin with a `session_started` event and an `action_listen`
        # as a user message follows
        return [SessionStarted(), ActionExecuted("action_listen")]