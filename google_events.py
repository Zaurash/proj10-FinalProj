# Date handling
import arrow # Replacement for datetime, based on moment.js
import datetime # But we still need time
import re

def tooShort(times, duration):
    """
    Strips a list of events, of events which are shorter than a
    given duration
    :param times: list of events
    :param duration: string
    :return: list of events
    """
    longEnough = []
    duration = re.findall(r'\d+', duration)
    durationMins = int(duration[1])
    durationHrs = int(duration[0])
    minutes = datetime.timedelta(minutes=durationMins)
    hours = datetime.timedelta(hours=durationHrs)
    for event in times:
        eventStart = arrow.get(event["start"]["dateTime"], "h:mm a MMM D YYYY")
        eventEnd = arrow.get(event["end"]["dateTime"], "h:mm a MMM D YYYY")
        if (eventStart + minutes + hours) < eventEnd:
            longEnough.append(event)

    return longEnough

def freeTimes(busyTimes, allTimes):
    """
    returns a list of free times
    :param busyTimes: list of events
    :param allTimes: list of events
    :return: list of events
    """
    freeTimes = []

    for freeEvent in allTimes:
        multiday = False
        freeEventDate = arrow.get(freeEvent["start"]["dateTime"]).date()
        freeTimeStart = arrow.get(freeEvent["start"]["dateTime"])
        for busyEvent in busyTimes:
            freeDate = arrow.get(freeEvent["start"]["dateTime"]).date()
            busyDateStart = arrow.get(busyEvent["start"]["dateTime"]).date()
            busyDateEnd = arrow.get(busyEvent["end"]["dateTime"]).date()
            if freeEventDate == busyDateStart:
                freeTimeEnd = arrow.get(busyEvent["start"]["dateTime"])
                if freeTimeStart.time() == freeTimeEnd.time():
                    freeTimeStart = arrow.get(busyEvent["end"]["dateTime"])
                    continue
                freeTime = {"summary": "Free Time on " + str(freeTimeStart),
                  "start": {"dateTime": freeTimeStart.format("h:mm a MMM D YYYY")},
                  "end": {"dateTime": freeTimeEnd.format("h:mm a MMM D YYYY")}}
                freeTimes.append(freeTime)
                freeTimeStart = arrow.get(busyEvent["end"]["dateTime"])
                if freeTimeStart.date() > freeDate:
                    multiday = True
            elif busyDateStart < freeDate < busyDateEnd:
                multiday = True
            elif busyDateStart < freeDate == busyDateEnd:
                freeTimeStart = arrow.get(busyEvent["end"]["dateTime"])
                continue
        if not multiday:
            freeTimeEnd = arrow.get(freeEvent["end"]["dateTime"])
            if freeTimeStart.time() != freeTimeEnd.time():
                freeTime = {"summary": "Free Time on " + str(freeTimeStart),
                          "start": {"dateTime": freeTimeStart.format("h:mm a MMM D YYYY")},
                          "end": {"dateTime": freeTimeEnd.format("h:mm a MMM D YYYY")}}
                freeTimes.append(freeTime)

    return freeTimes


def consolidateEvents(events):
    """
    Takes a list of events and returns a new list
    of events where any overlapping events have been joined,
    sorted by the event's start datetime.
    @param events: a list of events
    @return: a list of events
    """
    events = consolidateEventsRecursiveHelper(events)
    eventsFinal = []
    for event in events:
        if event != None:
            eventsFinal.append(event)

    eventsFinal.sort(key=lambda evnt: arrow.get(evnt["start"]["dateTime"]))

    return eventsFinal

def consolidateEventsRecursiveHelper(events):
    """
    Helper function for consolidateEvents; handles the
    recursive portion of the function.
    @param events: a list of events
    @return: a list of events
    """
    for i in range(len(events)):
        for j in range(len(events)):
            if events[i] == None or events[j] == None:
                continue
            # Skip this iteration if event and otherEvent are the same event
            if events[i] == events[j]:
                continue
            # If event and otherEvent overlap, replace event with
            # the union of other event and event and remove
            # otherEvent from events
            # print("CHECKING EVENTS: " + events[i]["summary"] + " AT " + str(arrow.get(events[i]["start"]["dateTime"]).time()) + " until " + str(arrow.get(events[i]["end"]["dateTime"]).time()) + " on " + str(arrow.get(events[i]["end"]["dateTime"]).date()))
            # print("                 " + events[j]["summary"] + " AT " + str(arrow.get(events[j]["start"]["dateTime"]).time()) + " until " + str(arrow.get(events[j]["end"]["dateTime"]).time()) + " on " + str(arrow.get(events[i]["end"]["dateTime"]).date()))
            if eventsOverlap(events[i], events[j]):
                union = eventsUnion(events[i], events[j])
                events.append(union)
                events[i] = None
                events[j] = None
                events = consolidateEventsRecursiveHelper(events)
    return events

def eventsUnion(event1, event2):
    """
    Returns an event of the union of two events
    @param event1: an event
    @param event2: an event
    @return: an event
    """
    if not eventsOverlap(event1, event2):
        raise ValueError('Events do not overlap!')
    returnEvent= {"summary": "Union of " + event1["summary"] + " and " + event2["summary"],
                  "start": {"dateTime": None},
                  "end": {"dateTime": None}}
    event1Start = arrow.get(event1["start"]["dateTime"])
    event1End = arrow.get(event1["end"]["dateTime"])
    event2Start = arrow.get(event2["start"]["dateTime"])
    event2End = arrow.get(event2["end"]["dateTime"])
    if event1Start <= event2Start and event1End <= event2End:
        returnEvent["start"]["dateTime"] = event1Start
        returnEvent["end"]["dateTime"] = event2End
    elif event1Start <= event2Start and event1End >= event2End:
        returnEvent["start"]["dateTime"] = event1Start
        returnEvent["end"]["dateTime"] = event1End
    elif event1Start >= event2Start and event1End <= event2End:
        returnEvent["start"]["dateTime"] = event2Start
        returnEvent["end"]["dateTime"] = event2End
    elif event1Start >= event2Start and event1End >= event2End:
        returnEvent["start"]["dateTime"] = event2Start
        returnEvent["end"]["dateTime"] = event1End
    return returnEvent

def eventsOverlap(event1, event2):
    """
    Returns true if two events overlap, false otherwise
    @param event1: an event
    @param event2: an event
    @return: boolean
    """
    event1Start = arrow.get(event1["start"]["dateTime"])
    event1End = arrow.get(event1["end"]["dateTime"])
    event2Start = arrow.get(event2["start"]["dateTime"])
    event2End = arrow.get(event2["end"]["dateTime"])
    if event1Start <= event2Start and event1End >= event2Start:
        return True
    elif event2Start <= event1Start and event2End >= event1Start:
        return True
    elif event1Start <= event2Start and event1End >= event2End:
        return True
    elif event2Start <= event1Start and event2End >= event1End:
        return True
    return False

def timeRangeContainsRange(event1Start, event2Start, event1End, event2End):
    """
    Returns true if one set of times starts and ends
    within another set of times
    @param event1Start: datetime
    @param event2Start: datetime
    @param event1End: datetime
    @param event2End: datetime
    @return: boolean
    """
    if event2Start <= event1Start and event2End >= event1End:
        return True
    elif event1Start <= event2Start and event1End >= event2End:
        return True
    else:
        return False