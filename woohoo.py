import sp
import os
import sys
import time
import threading

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)),"lib"))
from flask import Flask, request
from suntime import Sun
import requests


sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)),""))
from woohooHelper import Utils

class Woohoo(sp.BaseDevice):
    pluginInfo = {
        "name": "Woohoo",
        "category": "Vivid Studios",
        "description": "Woohoo agent communication",
        "keywords" : "Vivid,Woohoo",
        "author": "Stage Precision",
        "version": (1, 0),
        "spVersion": (1, 9, 0),
        #"helpPath": os.path.join(os.path.dirname(os.path.abspath(__file__)), "help.md"),
        "iconPath": os.path.join(os.path.dirname(os.path.abspath(__file__)), "woohoo-logo.svg")
    }

    def event_loop(self):
        self.restServer.add_url_rule("/calendar", "calendar", self.restGET_Calendar_Endpoint, methods=["GET"])
        self.restServer.add_url_rule("/calendar", "event", self.restPOST_Calendar_Endpoint, methods=["POST"])
        self.restServer.add_url_rule("/shutdown", "shutdown", self.shutdown, methods=["POST"])
        self.restServer.run(host=self.localIP.value, port=int(self.port.value), debug=False)

    def __init__(self):
        sp.BaseDevice.__init__(self)
        self.restServer = Flask(__name__)
        self.listener_thread = None

    def afterInit(self):
        self.showStatusArrow(True, True)

        self.localIP = self.objectContainer.addIPParameter("IP", True)
        self.port = self.objectContainer.addIntParameter("Port", 5000, 1, 65535)

        self.calendar = self.objectContainer.addTargetParameter("Calendar", True, "Calendar")
        self.stateMachine = self.objectContainer.addTargetParameter("StateMachine", True, "StateMachine")

        self.dayStart = self.objectContainer.addStringParameter("Day Start", "04:30 PM")
        self.dayEnd = self.objectContainer.addStringParameter("Day End", "03:00 AM")

        self.timecodeEventName = "pre_timecode_show_trigger"
        self.registerEvent("Pre Timecode Show Triggerd", self.timecodeEventName)
        self.timecodeActionName = "call_pre_timecode_event"
        self.addAction(self.timecodeActionName, "", self.actOnRunAction)

        self.shiftNextTCShow = self.addAction("Shift next TC Show", "", self.actShiftNextTCShow)
        self.shiftNextTCShow.addIntParameter("Time in sec", 0, 60, 86400)
       
        self.listener_thread = threading.Thread(target=self.event_loop, daemon=True)
        self.listener_thread.start()
    
    def shutdown(self):
        func = request.environ.get("werkzeug.server.shutdown")
        if func is None:
            pass
        func()
        return

    def actOnRunAction(self, callback):
        self.emitEvent(self.timecodeEventName)
        callback({})

    def actShiftNextTCShow(self, callback, _time):
        calendar = self._getCalendarFromtarget()
        calendarEntries = []

        linkedStateMachine = self._getStateMachineFromTarget()
        states = self._getStates(linkedStateMachine)

        for calendarEntry in calendar.entries.controllableContainers:
            for state in states:
                if state.name == calendarEntry.entry.value:
                    if state.isTc:
                        if calendarEntry.start.value > int(time.time() * 1000):
                            calendarEntries.append(calendarEntry)
        calendarEntries.sort(key=lambda e: e.start.value)
        if calendarEntries:
            calendarEntries[0].start.value = calendarEntries[0].start.value + _time*1000
            calendarEntries[0].end.value = calendarEntries[0].end.value + _time*1000
        callback({})

    def _getStateMachineFromTarget(self):
        for projectTreeObject in sp.engine.project.project.controllableContainers:
            if str(projectTreeObject.getControlAddress()) == self.stateMachine.value:
                return projectTreeObject

    def _getCalendarFromtarget(self):
        for projectTreeObject in sp.engine.project.project.controllableContainers:
            if str(projectTreeObject.getControlAddress()) == self.calendar.value:
                return projectTreeObject

    def _getAllCalendarEntries(self, calendar, searchStart, searchEnd):
        calendarEntries = [
            {
                "id": y.name,
                "state": y.entry.value,
                "start": y.start.value,
                "end": y.end.value,
            }
            for y in calendar.entries.controllableContainers
            if (y.end.value >= searchStart)
            and (y.start.value <= searchEnd)
            and not str(y.entry.value).startswith("***")
        ]
        return sorted(calendarEntries, key=lambda e: e["start"])

    def _getStates(self, linkedStateMachine):
        states: list[Utils.StatesValues] = []
        for name, col, length, type_, desc in zip(
            linkedStateMachine.columns.stateName.cells.controllableContainers,
            linkedStateMachine.columns.stateColor.cells.controllableContainers,
            linkedStateMachine.columns.stateLength.cells.controllableContainers,
            linkedStateMachine.columns.stateType.cells.controllableContainers,
            linkedStateMachine.columns.stateDescription.cells.controllableContainers
        ):
            isTC = length.mode.value == 0
            states.append(
                Utils.StatesValues(
                    str(name.content.value),
                    col.content.value,
                    isTC,
                    length.content.value,
                    type_.content.value,
                    desc.content.value,
                )
            )
        return states

    def restGET_Calendar_Endpoint(self):
        self.pushStatusInput()
        data = request.get_json()

        # Sunset and Sunrise
        latitude = 25.200368938106816
        longitude = 55.27662585508697
        sun = Sun(latitude, longitude)

        today_sr = sun.get_sunrise_time()   
        today_ss = sun.get_sunset_time()

        sunInfos = {
            "sun": {
                "sunrise": int(today_sr.timestamp()*1000),
                "sunset": int(today_ss.timestamp()*1000),
            }
        }

        filter_cfg = data.get("filter")
        if not filter_cfg or "day" not in filter_cfg or "month" not in filter_cfg or "year" not in filter_cfg:
            return Utils.error_response

        metainfos = {
            "time": {
                "timeformat": "integer -> Unix Timestamp  (Milliseconds (1/1,000 second) since Jan 01 1970. (UTC))",
                "currentTime": int(time.time() * 1000),
            }
        }

        filterInfos = {
            "filter": {
                "year": int(filter_cfg["year"]),
                "month": int(filter_cfg["month"]),
                "day": int(filter_cfg["day"])
            }
        }

        linkedStateMachine = self._getStateMachineFromTarget()
        states = self._getStates(linkedStateMachine)

        availableStates = [
            {
                "state": str(s.name),
                "type": str(s.type),
                "description": str(s.description),
                **({"timecode": int(s.length)} if s.isTc else {})
            }
            for s in states
        ]

        searchYear, searchMonth, searchDay = (
            filterInfos["filter"][k] for k in ("year", "month", "day")
        )

        searchStart, searchEnd = Utils.unix_time_range_ms(searchYear, searchMonth, searchDay, self.dayStart.value, self.dayEnd.value)

        calendarEntries = self._getAllCalendarEntries(self._getCalendarFromtarget(), searchStart, searchEnd)
        self.pushStatusOutput()
        return {**metainfos, **filterInfos, **sunInfos, "availableStates" : availableStates, "calendarEntries": calendarEntries}

    def restPOST_Calendar_Endpoint(self):
        self.pushStatusInput()
        data = request.get_json()

        filter_cfg = data.get("filter")
        if not filter_cfg or "year" not in filter_cfg or "month" not in filter_cfg or "day" not in filter_cfg:
            return Utils.error_response

        searchYear, searchMonth, searchDay = map(int, (
            filter_cfg["year"],
            filter_cfg["month"],
            filter_cfg["day"]
        ))

        searchStart, searchEnd = Utils.unix_time_range_ms(searchYear, searchMonth, searchDay, self.dayStart.value, self.dayEnd.value)

        calendar_cfg = data.get("calendarEntries")
        if isinstance(calendar_cfg, list):
            valid = True
            for item in calendar_cfg:
                if not isinstance(item, dict) or not all(k in item for k in ("start", "end", "id", "state")):
                    valid = False
                    break
            if not valid:
                return {"Error": "incorrect calendarEntries"}
        else:
            return {"Error": "NO calendarEntries"}

        linkedCalendar = self._getCalendarFromtarget()

        linkedStateMachine = self._getStateMachineFromTarget()

        states = self._getStates(linkedStateMachine)

        for entry in linkedCalendar.entries.controllableContainers:
            if entry.end.value < searchStart or entry.start.value > searchEnd:
                continue

            updated = next((cfg for cfg in calendar_cfg if entry.name == cfg["id"]), None)

            if updated:
                if entry.start.value != updated["start"]:
                    entry.start.value = updated["start"]
                if entry.end.value != updated["end"]:
                    entry.end.value = updated["end"]
                if entry.entry.value != updated["state"]:
                    entry.entry.value = updated["state"]
            else:
                linkedCalendar.delete_entry(str(entry.name).replace(" ", ""))

        for updated in calendar_cfg:
            if not any(s.name == updated["state"] for s in states):
                continue

            exists = any(
                entry.name == updated["id"]
                for entry in linkedCalendar.entries.controllableContainers
                if not (entry.end.value < searchStart or entry.start.value > searchEnd)
            )

            if not exists:
                linkedCalendar.add_entry(updated["state"],updated["start"],updated["end"],0,[1, 1, 1, 1],0,)

        for calendarEntry in linkedCalendar.entries.controllableContainers:
            for index, state in enumerate(states):
                if state.name == calendarEntry.entry.value:
                    calendarEntry.color.value = state.color

                    if state.isTc:
                        calendarEntry.end.value = calendarEntry.start.value + state.length * 1000

                    for action in list(calendarEntry.onStart.controllableContainers):
                        calendarEntry.onStart.removeItem(str(action.name).replace(" ", ""))

                    newAction = calendarEntry.onStart.addItem("BaseAction")
                    if newAction:
                        newAction.name = "execute_state"
                        newAction.host.setTargetWithAddon(self.stateMachine.value, "execute_state")
                        newAction.parameters.baseItem.param.row.value = index + 1

                    break
            else:
                linkedCalendar.delete_entry(str(calendarEntry.name).replace(" ", ""))

        for calendarEntry in linkedCalendar.entries.controllableContainers:
            for index, state in enumerate(states):
                if state.name == calendarEntry.entry.value:
                    if state.isTc:
                        linkedCalendar.add_entry("***"+calendarEntry.entry.value+"***",calendarEntry.start.value-60000,calendarEntry.start.value,0,state.color,0,)
                    break

        for calendarEntry in linkedCalendar.entries.controllableContainers:
            if str(calendarEntry.entry.value).startswith("***"):

                for action in list(calendarEntry.onStart.controllableContainers):
                        calendarEntry.onStart.removeItem(str(action.name).replace(" ", ""))

                newAction = calendarEntry.onStart.addItem("BaseAction")
                if newAction:
                    newAction.name = self.timecodeActionName
                    newAction.host.setTargetWithAddon("/project/project/Woohoo1", self.timecodeActionName)

        self.pushStatusOutput()
        return self._getAllCalendarEntries(linkedCalendar, searchStart, searchEnd) 

    def onParameterFeedback(self, parameter):
        pass
        #if parameter == self.localIP or self.port:
            #self._stopThread()
            #self._startThread()
            
    def _stopThread(self):
        if self.localIP.isValidIP():
            if self.listener_thread or self.listener_thread.is_alive():
                requests.post(f"http://{self.localIP.value}:{int(self.port.value)}/shutdown")
                self.listener_thread.join()
                self.listener_thread = None

    def _startThread(self):
        if self.localIP.isValidIP():
            if self.listener_thread is None:
                self.listener_thread = threading.Thread(target=self.event_loop, daemon=True)
                self.listener_thread.start()

    def onDisabling(self):
        self.showStatusArrow(False, False)
        self.setStatus(sp.StatusType.Disabled)

    def onEnabling(self):
        self.showStatusArrow(True, True)
        self.setStatus(sp.StatusType.Connecting)

    def shutdown(self):
        self.showStatusArrow(False, False)
        self._stopThread()
        self.setStatus(sp.StatusType.Disconnect)

if __name__ == "__main__":
    sp.registerPlugin(Woohoo)
