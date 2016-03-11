import flask
from flask import render_template
from flask import request
from flask import url_for
import uuid
import sys

import json
import logging

# Mongo database
from pymongo import MongoClient
from bson.objectid import ObjectId

# Functions for working on google events
from google_events import *

# Date handling 
import arrow # Replacement for datetime, based on moment.js
import datetime # But we still need time
from dateutil import tz  # For interpreting local times


# OAuth2  - Google library implementation for convenience
from oauth2client import client
import httplib2   # used in oauth2 flow

# Google API for services 
from apiclient import discovery

###
# Globals
###

import CONFIG

app = flask.Flask(__name__)

SCOPES = 'https://www.googleapis.com/auth/calendar.readonly'
CLIENT_SECRET_FILE = CONFIG.GOOGLE_LICENSE_KEY  ## You'll need this
APPLICATION_NAME = 'MeetMe class project'

#############################
#
#  Pages (routed from URLs)
#
#############################

@app.route("/")
@app.route("/index")
def index():
    app.logger.debug("Entering index")

    return render_template('index.html')

@app.route("/account", methods = ["POST"])
def account():
  app.logger.debug("Entering account")

  username = request.form.get("username")
  password = request.form.get("password")

  flask.session["username"] = username
  flask.session["password"] = password

  try:
      MONGO_URL = "mongodb://{}:{}@localhost:{}/proposals".format(username,password,CONFIG.MONGO_PORT)
      dbclient = MongoClient(MONGO_URL)
      db = dbclient.proposals
      global collection
      collection = db.dated
  except:
      print("Failure opening database.  Is Mongo running? Correct password?")
      sys.exit(1)

  if 'begin_date' not in flask.session:
    init_session_values()

  ## We'll need authorization to list calendars
  ## I wanted to put what follows into a function, but had
  ## to pull it back here because the redirect has to be a
  ## 'return'
  app.logger.debug("Checking credentials for Google calendar access")
  credentials = valid_credentials()
  if not credentials:
      app.logger.debug("Redirecting to authorization")
      return flask.redirect(flask.url_for('oauth2callback'))

  gcal_service = get_gcal_service(credentials)
  app.logger.debug("Returned from get_gcal_service")
  flask.session['calendars'] = list_calendars(gcal_service)
  flask.session['proposals'] = getProposals()
  return render_template('account.html')

@app.route("/home")
def home():
  app.logger.debug("Entering account")

  if 'begin_date' not in flask.session:
    init_session_values()

  ## We'll need authorization to list calendars
  ## I wanted to put what follows into a function, but had
  ## to pull it back here because the redirect has to be a
  ## 'return'
  app.logger.debug("Checking credentials for Google calendar access")
  credentials = valid_credentials()
  if not credentials:
      app.logger.debug("Redirecting to authorization")
      return flask.redirect(flask.url_for('oauth2callback'))

  gcal_service = get_gcal_service(credentials)
  app.logger.debug("Returned from get_gcal_service")
  flask.session['calendars'] = list_calendars(gcal_service)
  flask.session['proposals'] = getProposals()
  return render_template('account.html')

@app.route('/oauth2callback')
def oauth2callback():
  """
  The 'flow' has this one place to call back to.  We'll enter here
  more than once as steps in the flow are completed, and need to keep
  track of how far we've gotten. The first time we'll do the first
  step, the second time we'll skip the first step and do the second,
  and so on.
  """
  app.logger.debug("Entering oauth2callback")
  flow =  client.flow_from_clientsecrets(
      CLIENT_SECRET_FILE,
      scope= SCOPES,
      redirect_uri=flask.url_for('oauth2callback', _external=True))
  ## Note we are *not* redirecting above.  We are noting *where*
  ## we will redirect to, which is this function.

  ## The *second* time we enter here, it's a callback
  ## with 'code' set in the URL parameter.  If we don't
  ## see that, it must be the first time through, so we
  ## need to do step 1.
  app.logger.debug("Got flow")
  if 'code' not in flask.request.args:
    app.logger.debug("Code not in flask.request.args")
    auth_uri = flow.step1_get_authorize_url()
    return flask.redirect(auth_uri)
    ## This will redirect back here, but the second time through
    ## we'll have the 'code' parameter set
  else:
    ## It's the second time through ... we can tell because
    ## we got the 'code' argument in the URL.
    app.logger.debug("Code was in flask.request.args")
    auth_code = flask.request.args.get('code')
    credentials = flow.step2_exchange(auth_code)
    flask.session['credentials'] = credentials.to_json()
    ## Now I can build the service and execute the query,
    ## but for the moment I'll just log it and go back to
    ## the main screen
    app.logger.debug("Got credentials")
    return flask.redirect(flask.url_for('home'))

@app.route("/_clear", methods = ["POST"])
def clear():
    collection.drop()
    app.logger.debug("Cleared Memos")

    return flask.redirect(url_for("home"))

@app.route("/save", methods = ["POST"])
def save():
    checkedEventsTitles = request.form.getlist("checkedEvent")
    checkedEvents= []

    for title in checkedEventsTitles:
        for event in flask.session["freeTimes"]:
            if event["summary"] == title:
                checkedEvents.append(event)

    record = {"type": "proposal",
              "title": flask.session["title"],
              "duration": flask.session["duration"],
              "location": flask.session["location"],
              "events": checkedEvents
              }
    collection.insert(record)
    app.logger.debug("Saved Proposal")
    return flask.redirect(url_for("home"))

@app.route('/new', methods=['POST'])
def new():
    return render_template('new.html')

@app.route('/view', methods=['POST'])
def view():
    proposalID = request.form.get("propID")
    proposalID = ObjectId(proposalID)
    proposal = collection.find_one({"_id": proposalID})
    flask.session["viewedProposal"] = {
                                       "title": proposal["title"],
                                       "duration": proposal["duration"],
                                       "location": proposal["location"],
                                       "events": proposal["events"]
                                       }
    return render_template('view.html')

@app.route('/proposal', methods=['POST'])
def proposal():
    checkedEventsIDs = request.form.getlist("checkedEvent")
    busyEvents = []
    for event in flask.session["busyEvents"]:
        for id in checkedEventsIDs:
            if event["id"] == id:
                busyEvents.append(event)

    busyEvents = consolidateEvents(busyEvents)

    for event in busyEvents:
        eventStart = arrow.get(event["start"]["dateTime"])
        eventEnd = arrow.get(event["end"]["dateTime"])
        print("Busy  at : " + event["summary"])
        print("     from: " + eventStart.format("h:mm a MMM D YYYY"))
        print("     until: " + eventEnd.format("h:mm a MMM D YYYY"))
        print("     type: " + str(type(eventEnd)))

    # Make events for all days in our date and time range

    freeTimeEvents = []
    day = datetime.timedelta(days=1)

    startDate = arrow.get(flask.session["begin_date"]).date()
    endDate = arrow.get(flask.session["end_date"]).date()
    startTime = arrow.get(flask.session["begin_time"], "h:mm A").time()
    endTime = arrow.get(flask.session["end_time"], "h:mm A").time()

    while startDate <= endDate:
        freeEvent= {"summary": "Free Time on " + str(startDate),
                  "start": {"dateTime": arrow.get(str(startDate) + " " + str(startTime), "YYYY-MM-DD HH:mm")},
                  "end": {"dateTime": arrow.get(str(startDate) + " " + str(endTime), "YYYY-MM-DD HH:mm")}}
        freeTimeEvents.append(freeEvent)
        startDate = startDate + day

    meetingTimes = freeTimes(busyEvents, freeTimeEvents)

    duration = flask.session["duration"]
    meetingTimes = tooShort(meetingTimes , duration)

    for event in meetingTimes:
        eventStart = event["start"]["dateTime"]
        eventEnd = event["end"]["dateTime"]
        print("Free  at : " + event["summary"])
        print("     from: " + str(eventStart))
        print("     until: " + str(eventEnd))
        print("     type: " + str(type(eventEnd)))

    flask.session["freeTimes"] = meetingTimes

    return render_template('proposal.html')

@app.route('/conflicts', methods=['POST'])
def conflicts():
    flask.session["selected_cals"] = request.form.getlist("checkedCal")
    app.logger.debug("Checking credentials for Google calendar access")
    credentials = valid_credentials()
    if not credentials:
      app.logger.debug("Redirecting to authorization")
      return flask.redirect(flask.url_for('oauth2callback'))

    gcal_service = get_gcal_service(credentials)
    app.logger.debug("Returned from get_gcal_service")

    busyEvents = []
    for cal in list_calendars(gcal_service):
        for selectedCalID in flask.session["selected_cals"]:
            if cal["id"] == selectedCalID:
                events = gcal_service.events().list(calendarId=cal["id"]).execute()
                for event in events['items']:
                    if ("transparency" in event) and event["transparency"] == "transparent":
                        continue
                    if "dateTime" in event["start"]:
                        eventStart = arrow.get(event["start"]["dateTime"])
                        eventEnd = arrow.get(event["end"]["dateTime"])
                        if eventStart.date() >= arrow.get(flask.session['begin_date']).date()\
                                and eventEnd.date() <= arrow.get(flask.session['end_date']).date():
                            if timeRangeContainsRange(eventStart.time(), arrow.get(flask.session["begin_time"], "h:mm A").time(),
                                                      eventEnd.time(), arrow.get(flask.session["end_time"], "h:mm A").time()):
                                # Event is a busy event and within our time frame
                                busyEvents.append(event)

    flask.session["busyEvents"] = busyEvents
    return render_template('conflicts.html')

@app.route('/calendars', methods=['POST'])
def calendars():
    """
    User chose a date range with the bootstrap daterange
    widget.
    """
    app.logger.debug("Entering setrange")
    flask.flash("Setrange gave us '{}'".format(request.form.get('daterange')) + ", " + request.form.get('begin_time') + " - " + request.form.get('end_time'))
    daterange = request.form.get('daterange')
    flask.session['daterange'] = daterange
    daterange_parts = daterange.split()
    flask.session['begin_date'] = interpret_date(daterange_parts[0])
    flask.session['end_date'] = interpret_date(daterange_parts[2])
    flask.session['begin_time'] = request.form.get('begin_time')
    flask.session['end_time'] = request.form.get('end_time')
    flask.session["title"] = request.form.get('title')
    flask.session["duration"] = request.form.get('duration')
    flask.session["location"] = request.form.get('location')
    app.logger.debug("Setrange parsed {} - {}  dates as {} - {}".format(
      daterange_parts[0], daterange_parts[1],
      flask.session['begin_date'], flask.session['end_date']))
    return render_template('calendars.html')

###
#
#  Google calendar authorization:
#      Returns us to the main /choose screen after inserting
#      the calendar_service object in the session state.  May
#      redirect to OAuth server first, and may take multiple
#      trips through the oauth2 callback function.
#
#  Protocol for use ON EACH REQUEST: 
#     First, check for valid credentials
#     If we don't have valid credentials
#         Get credentials (jump to the oauth2 protocol)
#         (redirects back to /choose, this time with credentials)
#     If we do have valid credentials
#         Get the service object
#
#  The final result of successful authorization is a 'service'
#  object.  We use a 'service' object to actually retrieve data
#  from the Google services. Service objects are NOT serializable ---
#  we can't stash one in a cookie.  Instead, on each request we
#  get a fresh serivce object from our credentials, which are
#  serializable. 
#
#  Note that after authorization we always redirect to /choose;
#  If this is unsatisfactory, we'll need a session variable to use
#  as a 'continuation' or 'return address' to use instead. 
#
####


def valid_credentials():
    """
    Returns OAuth2 credentials if we have valid
    credentials in the session.  This is a 'truthy' value.
    Return None if we don't have credentials, or if they
    have expired or are otherwise invalid.  This is a 'falsy' value. 
    """
    if 'credentials' not in flask.session:
      return None

    credentials = client.OAuth2Credentials.from_json(
        flask.session['credentials'])

    if (credentials.invalid or
        credentials.access_token_expired):
      return None
    return credentials


def get_gcal_service(credentials):
  """
  We need a Google calendar 'service' object to obtain
  list of calendars, busy times, etc.  This requires
  authorization. If authorization is already in effect,
  we'll just return with the authorization. Otherwise,
  control flow will be interrupted by authorization, and we'll
  end up redirected back to /choose *without a service object*.
  Then the second call will succeed without additional authorization.
  """
  app.logger.debug("Entering get_gcal_service")
  http_auth = credentials.authorize(httplib2.Http())
  service = discovery.build('calendar', 'v3', http=http_auth)
  app.logger.debug("Returning service")
  return service

####
#
#   Initialize session variables 
#
####

def init_session_values():
    """
    Start with some reasonable defaults for date and time ranges.
    Note this must be run in app context ... can't call from main. 
    """
    # Default date span = tomorrow to 1 week from now
    now = arrow.now('local')
    tomorrow = now.replace(days=+1)
    nextweek = now.replace(days=+7)
    flask.session["begin_date"] = tomorrow.floor('day').isoformat()
    flask.session["end_date"] = nextweek.ceil('day').isoformat()
    flask.session["daterange"] = "{} - {}".format(
        tomorrow.format("MM/DD/YYYY"),
        nextweek.format("MM/DD/YYYY"))
    # Default time span each day, 8 to 5
    flask.session["begin_time"] = "9:00 AM"
    flask.session["end_time"] = "5:00 PM"

def getProposals():
    """
    Returns all proposals in the database, in a form that
    can be inserted directly in the 'session' object.
    """
    records = []
    for record in collection.find( { "type": "proposal" } ):
        record['_id'] = str(record['_id'])
        record["duration"] = str(record["duration"])
        record["title"] = str(record["title"])
        record["loaction"] = str(record["location"])
        records.append(record)
    records = sorted(records, key=lambda k: k['title'])
    return records

#####
#
#  Option setting:  Buttons or forms that add some
#     information into session state.  Don't do the
#     computation here; use of the information might
#     depend on what other information we have.
#   Setting an option sends us back to the main display
#      page, where we may put the new information to use.
#
#####

def interpret_time( text ):
    """
    Read time in a human-compatible format and
    interpret as ISO format with local timezone.
    May throw exception if time can't be interpreted. In that
    case it will also flash a message explaining accepted formats.
    """
    app.logger.debug("Decoding time '{}'".format(text))
    time_formats = ["ha", "h:mma",  "h:mm a", "H:mm"]
    try: 
        as_arrow = arrow.get(text, time_formats).replace(tzinfo=tz.tzlocal())
        app.logger.debug("Succeeded interpreting time")
    except:
        app.logger.debug("Failed to interpret time")
        flask.flash("Time '{}' didn't match accepted formats 13:30 or 1:30pm"
              .format(text))
        raise
    return as_arrow.isoformat()

def interpret_date( text ):
    """
    Convert text of date to ISO format used internally,
    with the local time zone.
    """
    try:
      as_arrow = arrow.get(text, "MM/DD/YYYY").replace(
          tzinfo=tz.tzlocal())
    except:
        flask.flash("Date '{}' didn't fit expected format 12/31/2001")
        raise
    return as_arrow.isoformat()

def next_day(isotext):
    """
    ISO date + 1 day (used in query to Google calendar)
    """
    as_arrow = arrow.get(isotext)
    return as_arrow.replace(days=+1).isoformat()

####
#
#  Functions (NOT pages) that return some information
#
####
  
def list_calendars(service):
    """
    Given a google 'service' object, return a list of
    calendars.  Each calendar is represented by a dict, so that
    it can be stored in the session object and converted to
    json for cookies. The returned list is sorted to have
    the primary calendar first, and selected (that is, displayed in
    Google Calendars web app) calendars before unselected calendars.
    """
    app.logger.debug("Entering list_calendars")  
    calendar_list = service.calendarList().list().execute()["items"]
    result = [ ]
    for cal in calendar_list:
        kind = cal["kind"]
        id = cal["id"]
        if "description" in cal: 
            desc = cal["description"]
        else:
            desc = "(no description)"
        summary = cal["summary"]
        # Optional binary attributes with False as default
        selected = ("selected" in cal) and cal["selected"]
        primary = ("primary" in cal) and cal["primary"]
        

        result.append(
          { "kind": kind,
            "id": id,
            "summary": summary,
            "selected": selected,
            "primary": primary
            })
    return sorted(result, key=cal_sort_key)


def cal_sort_key( cal ):
    """
    Sort key for the list of calendars:  primary calendar first,
    then other selected calendars, then unselected calendars.
    (" " sorts before "X", and tuples are compared piecewise)
    """
    if cal["selected"]:
       selected_key = " "
    else:
       selected_key = "X"
    if cal["primary"]:
       primary_key = " "
    else:
       primary_key = "X"
    return (primary_key, selected_key, cal["summary"])


#################
#
# Functions used within the templates
#
#################

@app.template_filter( 'fmtdate' )
def format_arrow_date( date ):
    try: 
        normal = arrow.get( date )
        return normal.format("ddd MM/DD/YYYY")
    except:
        return "(bad date)"

@app.template_filter( 'fmttime' )
def format_arrow_time( time ):
    try:
        normal = arrow.get( time )
        return normal.format("HH:mm")
    except:
        return "(bad time)"
    
#############


if __name__ == "__main__":
  # App is created above so that it will
  # exist whether this is 'main' or not
  # (e.g., if we are running in a CGI script)

  app.secret_key = str(uuid.uuid4())  
  app.debug=CONFIG.DEBUG
  app.logger.setLevel(logging.DEBUG)
  # We run on localhost only if debugging,
  # otherwise accessible to world
  if CONFIG.DEBUG:
    # Reachable only from the same computer
    app.run(port=CONFIG.PORT)
  else:
    # Reachable from anywhere 
    app.run(port=CONFIG.PORT,host="0.0.0.0")
    
