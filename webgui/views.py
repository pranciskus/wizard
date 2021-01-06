from django.shortcuts import render
from django.http import JsonResponse

from time import time
import random
from json import loads
from webgui.models import Server

def get_random_string(length):
    # put your letters in the following string
    sample_letters = 'abcdefghi'
    result_str = ''.join((random.choice(sample_letters) for i in range(length)))
    return result_str

def get_json(request, server_id: int):
  server = Server.objects.get(pk=server_id)
  ungrouped_vehicles = server.entries.all()
  vehicle_groups = {}
  for vehicle in ungrouped_vehicles:
    component = vehicle.component
    steam_id = component.steam_id
    version = component.component_version
    name = component.component_name
    do_update = component.do_update
    short_name = component.short_name

    if steam_id not in vehicle_groups:
      vehicle_groups[steam_id] = {
        "entries": [],
        "component": {
          "version": version,
          "name": name,
          "update": do_update,
          "short": short_name,
          "numberplates": []
        }
      }
    vehicle_groups[steam_id]["entries"].append("{}#{}".format(vehicle.team_name, vehicle.vehicle_number))
  
  tracks = server.tracks.all()

  conditions = server.conditions
  rfm_url = conditions.rfm.url

  track_groups = {}
  for track in tracks:
    track_component = track.component
    track_groups[track_component.steam_id] = {
      "layout": track.layout,
      "component": {
        "version": track_component.component_version,
        "name": track_component.component_name,
        "update": False
      }
    }

  result = {
    "server": {
      "Multiplayer.JSON": loads(server.overwrites_multiplayer),
      "Player.JSON": {},
      "cars": vehicle_groups,
      "track": track_groups,
      "Mod": {
        "name": "apx_",
        "version":"1.0.{}".format(get_random_string(5)),
        "rfm": rfm_url
      }
    }
  }
  return JsonResponse(result)