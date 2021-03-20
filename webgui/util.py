from wizard.settings import (
    APX_ROOT,
    MEDIA_ROOT,
    PACKS_ROOT,
    DISCORD_WEBHOOK,
    DISCORD_WEBHOOK_NAME,
    DISCORD_RACE_CONTROL_WEBHOOK,
    DISCORD_RACE_CONTROL_WEBHOOK_NAME,
    INSTANCE_NAME,
    OPENWEATHERAPI_KEY,
)
import hashlib
import subprocess
from django.dispatch import receiver
from os.path import join, exists
from os import mkdir
from . import models
from json import loads, dumps
import random
from django.core.exceptions import ValidationError
from django.db.models.signals import post_save
import socket
import discord
from requests import post

FILE_NAME_SUFFIXES = [
    ".json",
    ".dds",
    "WINDOWSIN.dds",
    "WINDOWSOUT.dds",
    "_Region.dds",
    "helmet.dds",
    "icon.png",
    "SMicon.dds",
    "icon.dds",
    "helmet.png",
    "-icon-128x72.png",
    "-icon-256x144.png",
    "-icon-512x288.png",
    "-icon-1024x576.png",
    "-icon-2048x1152.png",
]


RECIEVER_COMP_INFO = "pre-beta"


def get_update_filename(instance, filename):
    component_name = instance.component_name
    user_root = get_hash(str(instance.user.pk))
    full_user_path = join(MEDIA_ROOT, user_root)
    if not exists(full_user_path):
        mkdir(full_user_path)

    liveries_path = join(full_user_path, "liveries")
    if not exists(liveries_path):
        mkdir(liveries_path)

    component_path = join(liveries_path, component_name)
    if not exists(component_path):
        mkdir(component_path)

    return join(user_root, "liveries", component_name, filename)


def get_livery_mask_root(instance, filename):
    root_path = join(MEDIA_ROOT, get_hash(str(instance.user.pk)), "templates")
    if not exists(root_path):
        mkdir(root_path)
    return join(join(get_hash(str(instance.user.pk)), "templates"), filename)


def get_conditions_file_root(instance, filename):
    user_root = get_hash(str(instance.user.pk))
    full_path = join(MEDIA_ROOT, user_root)
    if not exists(full_path):
        mkdir(full_path)
    conditions_path = join(full_path, "conditions")
    if not exists(conditions_path):
        mkdir(conditions_path)
    return join(user_root, "conditions", filename)


def livery_filename(instance, filename):
    vehicle_number = instance.entry.vehicle_number
    component_short_name = instance.entry.component.short_name
    component_name = instance.entry.component.component_name
    user_root = get_hash(str(instance.user.pk))
    full_user_path = join(MEDIA_ROOT, user_root)
    if not exists(full_user_path):
        mkdir(full_user_path)

    liveries_path = join(full_user_path, "liveries")
    if not exists(liveries_path):
        mkdir(liveries_path)

    component_path = join(liveries_path, component_name)
    if not exists(component_path):
        mkdir(component_path)

    selected_suffix = None
    for suffix in FILE_NAME_SUFFIXES:
        if str(filename).endswith(suffix):
            selected_suffix = suffix
    if selected_suffix is None:
        raise ValidationError("We can't identify that file purpose")
    new_file_path = join(
        user_root,
        "liveries",
        component_name,
        "{}_{}{}".format(component_short_name, vehicle_number, selected_suffix),
    )
    return new_file_path


def get_key_root_path(instance, filename):
    hash_code = get_server_hash(instance.url)
    full_path = join(MEDIA_ROOT, "keys", hash_code)
    if not exists(full_path):
        mkdir(full_path)
    return join("keys", hash_code, filename)


def get_logfile_root_path(instance, filename):
    hash_code = get_server_hash(instance.url)
    full_path = join(MEDIA_ROOT, "logs", hash_code)
    if not exists(full_path):
        mkdir(full_path)
    return join("keys", hash_code, filename)


def get_random_string(length):
    # put your letters in the following string
    sample_letters = "abcdefghi"
    result_str = "".join((random.choice(sample_letters) for i in range(length)))
    return result_str


def get_hash(input):
    sha_1 = hashlib.sha1()
    sha_1.update(input.encode("utf-8"))
    key = str(sha_1.hexdigest())
    return key


def get_server_hash(url):
    return get_hash(url)


def run_apx_command(hashed_url, commandline):
    apx_path = join(APX_ROOT, "apx.py")
    command_line = "python {} --server {} {}".format(apx_path, hashed_url, commandline)
    got = subprocess.check_output(command_line, cwd=APX_ROOT, shell=True).decode(
        "utf-8"
    )
    return got


def get_event_config(event_id: int):
    server = models.Event.objects.get(pk=event_id)
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
                    "numberplates": [],
                },
            }
        vehicle_groups[steam_id]["entries"].append(
            "{}#{}".format(vehicle.team_name, vehicle.vehicle_number)
        )

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
                "update": False,
            },
        }
    if not server.mod_name or len(server.mod_name) == 0:
        mod_name = "apx_{}".format(get_server_hash(server.name)[:8])
    else:
        mod_name = server.mod_name
    # grip settings

    sessions = conditions.sessions.all()
    session_list = {}
    session_setting_list = []
    if len(sessions) > 0:
        for session in sessions:
            session_list[session.type] = session.grip.path
            session_setting_list.append(
                {
                    "type": str(session.type),
                    "length": session.length,
                    "laps": session.laps,
                    "start": str(session.start),
                }
            )
    else:
        session_list = None

    start_type = 0
    if server.start_type == models.EvenStartType.FLS:
        start_type = 1
    if server.start_type == models.EvenStartType.SCR:
        start_type = 2
    if server.start_type == models.EvenStartType.FR:
        start_type = 4

    result = {
        "server": {
            "overwrites": {
                "Multiplayer.JSON": loads(server.overwrites_multiplayer),
                "Player.JSON": loads(server.overwrites_player),
            }
        },
        "conditions": session_list,
        "sessions": session_setting_list,
        "cars": vehicle_groups,
        "track": track_groups,
        "start_type": start_type,
        "real_weather": server.real_weather,
        "real_weather_key": OPENWEATHERAPI_KEY,
        "temp_offset": server.temp_offset,
        "comp": RECIEVER_COMP_INFO,
        "mod": {
            "name": mod_name,
            "version": "1.0.{}".format(get_random_string(5)),
            "rfm": rfm_url,
        },
    }
    return result


def do_post(message):
    if DISCORD_WEBHOOK is not None and DISCORD_WEBHOOK_NAME is not None:
        got = post(
            DISCORD_WEBHOOK,
            json={
                "username": DISCORD_WEBHOOK_NAME,
                "content": message,
                "avatar_url": "",
            },
            headers={"Content-type": "application/json"},
        )


def do_rc_post(message):
    if (
        DISCORD_RACE_CONTROL_WEBHOOK is not None
        and DISCORD_RACE_CONTROL_WEBHOOK_NAME is not None
    ):
        got = post(
            DISCORD_RACE_CONTROL_WEBHOOK,
            json={
                "username": DISCORD_RACE_CONTROL_WEBHOOK_NAME,
                "content": message,
                "avatar_url": "",
            },
            headers={"Content-type": "application/json"},
        )


def create_virtual_config():
    all_servers = models.Server.objects.all()
    server_data = {}
    for server in all_servers:
        key = get_server_hash(server.url)
        # we assume that the liveries folder may already be existing
        build_path = join(MEDIA_ROOT, get_hash(str(server.user.pk)), "liveries")
        packs_path = join(PACKS_ROOT, get_hash(str(server.user.pk)))
        templates_path = join(MEDIA_ROOT, get_hash(str(server.user.pk)), "templates")
        if not exists(packs_path):
            mkdir(packs_path)

        if not exists(build_path):
            mkdir(build_path)

        if not exists(templates_path):
            mkdir(templates_path)
        server_data[key] = {
            "url": server.url,
            "secret": server.secret,
            "public_ip": server.public_ip,
            "env": {
                "build_path": build_path,
                "packs_path": packs_path,
                "templates_path": templates_path,
            },
        }

    servers_json_path = join(APX_ROOT, "servers.json")
    with open(servers_json_path, "w") as file:
        file.write(dumps(server_data))


def do_server_interaction(server):
    secret = server.secret
    url = server.url
    key = get_server_hash(url)
    if server.action == "S+":
        try:
            run_apx_command(key, "--cmd start")
            do_post(
                "[{}]: 🚀 Starting looks complete for {}!".format(
                    INSTANCE_NAME, server.name
                )
            )
        except Exception as e:
            print(e)
            do_post(
                "[{}]: 😱 Failed starting server {}: {}".format(
                    INSTANCE_NAME, server.name, str(e)
                )
            )
        finally:
            server.action = ""
            server.locked = False
            server.save()

    if server.action == "R-":

        try:
            run_apx_command(key, "--cmd stop")
            do_post(
                "[{}]: 🛑 Stopping looks complete for {}!".format(
                    INSTANCE_NAME, server.name
                )
            )
        except Exception as e:
            do_post(
                "[{}]: 😱 Failed to stop server {}: {}".format(
                    INSTANCE_NAME, server.name, str(e)
                )
            )
        finally:
            server.action = ""
            server.locked = False
            server.save()

    if server.action == "D":
        # save event json
        event_config = get_event_config(server.event.pk)
        event_config["branch"] = server.branch
        config_path = join(APX_ROOT, "configs", key + ".json")
        with open(config_path, "w") as file:
            file.write(dumps(event_config))
        # save rfm
        rfm_path = join(MEDIA_ROOT, server.event.conditions.rfm.name)

        try:
            command_line = "--cmd build_skins --args {} {}".format(
                config_path, rfm_path
            )
            run_apx_command(key, command_line)
            command_line = "--cmd deploy --args {} {}".format(config_path, rfm_path)
            run_apx_command(key, command_line)
            do_post(
                "[{}]: 😎 Deployment looks good for {}!".format(
                    INSTANCE_NAME, server.name
                )
            )
        except Exception as e:
            do_post(
                "[{}]: 😱 Failed deploying server {}: {}".format(
                    INSTANCE_NAME, server.name, str(e)
                )
            )
        finally:
            server.action = ""
            server.locked = False
            server.save()