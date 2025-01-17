from django.db import models
from django.core.exceptions import ValidationError

# from django.conf import settings
# from django import forms
# from shutil import copy, rmtree
from os import remove, linesep, unlink, system, mkdir
from os.path import exists, join, basename, isfile
from collections import OrderedDict
import json
from json.decoder import JSONDecodeError

# from django.contrib import messages
from django.core.validators import RegexValidator, MinValueValidator, MaxValueValidator
from webgui.util import (
    merge_dicts,
    livery_filename,
    track_filename,
    run_apx_command,
    get_server_hash,
    get_key_root_path,
    # get_logfile_root_path,
    get_conditions_file_root,
    get_update_filename,
    # get_hash,
    get_livery_mask_root,
    get_random_string,
    create_virtual_config,
    do_server_interaction,
    # get_component_file_root,
    # RECIEVER_COMP_INFO,
    get_plugin_root_path,
    create_firewall_script,
    get_random_short_name,
    get_speedtest_result,
)
from wizard.settings import (
    BASE_DIR,
    # FAILURE_THRESHOLD,
    MEDIA_ROOT,
    STATIC_URL,
    MAX_SERVERS,
    MAX_UPSTREAM_BANDWIDTH,
    MAX_DOWNSTREAM_BANDWIDTH,
    MAX_STEAMCMD_BANDWIDTH,
    USE_GLOBAL_STEAMCMD,
    EASY_MODE,
    ADD_PREFIX,
)
from webgui.storage import OverwriteStorage
from django.utils.html import mark_safe
import re
from re import match
from django.db.models.signals import post_save
from django.dispatch import receiver

# from datetime import datetime
from threading import Thread

import logging

logger = logging.getLogger(__name__)

USE_WAND = True
try:
    from wand import image
    from wand.drawing import Drawing
    from wand.color import Color
except ImportError:
    USE_WAND = False
    logger.info("Wand will not be available.")

status_map = {}
state_map = {}
session_map = {}


MOD_WARNINGS = {
    "1737056846": "The Nordschleife DLC is more than 2.8 Gigabytes large. Due to steamcmd, downloads of these sizes tend to abort. Consider uploading this mod by hand to the server and use it as a file based item: https://wiki.apx.chmr.eu/doku.php?id=file_based_content",  # noqa: E501
    "2141682966": "The Portland DLC is more than 1.2 Gigabytes large. Due to steamcmd, downloads of these sizes tend to abort. Consider uploading this mod by hand to the server and use it as a file based item: https://wiki.apx.chmr.eu/doku.php?id=file_based_content",  # noqa: E501
    "2121171862": "The GDB files of this mod are flawed with the issue that slashes for comments and quotes are included within names. Some layouts might not work which affects the addition of grip settings.",  # noqa: E501
    "788866138": "This mod is quite large (apparently 5 gigabytes). Steamcmd won't be able to download this reliable. Consider uploading this mod by hand to the server and use it as a file based item: https://wiki.apx.chmr.eu/doku.php?id=file_based_content",  # noqa: E501
    "2188673436": "This mod has 4.2 Gigabyte download. Due to steamcmd, downloads of these sizes tend to abort. Consider uploading this mod by hand to the server and use it as a file based item: https://wiki.apx.chmr.eu/doku.php?id=file_based_content",  # noqa: E501
}


class ComponentType(models.TextChoices):
    VEHICLE = "VEH", "Vehicle"
    LOCATION = "LOC", "Location"


class RaceSessionsType(models.TextChoices):
    TD = "TD", "Training Day"
    P1 = "P1", "Practice 1"
    Q1 = "Q1", "Qualy 1"
    WU = "WU", "Warmup"
    R1 = "R1", "Race 1"


class RaceSessionGripScale(models.TextChoices):
    SL = "-1", "scaled with session length"
    S = (
        "0",
        "static",
    )
    S_0_1 = "0.1", "0.1x"
    S_0_2 = "0.2", "0.2x"
    S_0_3 = "0.3", "0.3x"
    S_0_4 = "0.4", "0.4x"
    S_0_5 = "0.5", "0.5x"
    S_0_6 = "0.6", "0.6x"
    S_0_7 = "0.7", "0.7x"
    S_0_8 = "0.8", "0.8x"
    S_0_9 = "0.9", "0.9x"
    N = "1", "normal"
    F_1_5 = "1.5", "1.5x"
    F_2 = "2", "2x"
    F_3 = "3", "3x"
    F_4 = "4", "4x"
    F_5 = "5", "5x"
    F_6 = "6", "6x"
    F_7 = "7", "7x"
    F_8 = "8", "8x"
    F_9 = "9", "9x"
    F_10 = "10", "10x"
    F_11 = "11", "11x"
    F_12 = "12", "12x"
    F_13 = "13", "13x"
    F_14 = "14", "14x"
    F_15 = "15", "15x"


class RaceSessionFinishType(models.TextChoices):
    PL = "-2", "%laps"
    PT = "-1", "%time"
    PLT = "0", "%laps&time"
    CL = "1", "laps"
    CT = "2", "time"
    CLT = "3", "laps&time"


alphanumeric_validator = RegexValidator(
    r"^[0-9a-zA-Z_-]*$", "Only alphanumeric characters and dashes are allowed."
)

alphanumeric_validator_dots = RegexValidator(
    r"^[0-9a-zA-Z.\%]*$", "Only alphanumeric characters and dots are allowed."
)


def event_name_validator(value):
    max_length = 26 if not ADD_PREFIX else 21
    if len(value) > max_length:
        raise ValidationError(
            f"The event name is too long. You have {max_length} chars to use."
        )


class Component(models.Model):

    type = models.CharField(
        max_length=3, choices=ComponentType.choices, default=ComponentType.VEHICLE
    )
    steam_id = models.BigIntegerField(default=0, blank=True)
    base_component = models.ForeignKey(
        "Component", on_delete=models.CASCADE, blank=True, null=True
    )
    component_name = models.CharField(
        default="Example_Mod",
        max_length=200,
        help_text="This is the folder name inside Installed/Vehicles/ or Installed/Locations/",
    )
    alternative_name = models.CharField(
        default=None,
        null=True,
        blank=True,
        max_length=200,
        help_text="Alternative display name to keep same mods with different components apart",
    )
    is_official = models.BooleanField(
        default=False,
        help_text="Is official content which follows the even version and uneven version scheme (APX will select versions for you). If not checked, we will use the version you've selected.",  # noqa: E501
    )
    short_name = models.CharField(
        default=get_random_short_name,
        max_length=200,
        help_text="The short name is required to idenitfy (livery) filenames belonging to this component. You only need this when 'Do update' is checked.",
        validators=[alphanumeric_validator],
    )

    component_files = models.FileField(
        upload_to=get_update_filename, storage=OverwriteStorage, null=True, blank=True
    )

    update = models.FileField(
        upload_to=get_update_filename, storage=OverwriteStorage, null=True, blank=True
    )
    numberplate_template_l = models.FileField(
        upload_to=get_livery_mask_root,
        null=True,
        blank=True,
        max_length=255,
        help_text="A dds file containing the left numberplate background. Numbers will be applied.",
    )
    numberplate_template_mask_l = models.FileField(
        upload_to=get_livery_mask_root,
        null=True,
        blank=True,
        max_length=255,
        help_text="A dds file containing the region information for the left numberplate. Will be added on top of a given _Region.dds file.",
    )
    numberplate_template_r = models.FileField(
        upload_to=get_livery_mask_root,
        null=True,
        blank=True,
        max_length=255,
        help_text="A dds file containing the right numberplate background. Numbers will be applied.",
    )
    numberplate_template_mask_r = models.FileField(
        upload_to=get_livery_mask_root,
        null=True,
        blank=True,
        max_length=255,
        help_text="A dds file containing the region information for the leftright numberplate. Will be added on top of a given _Region.dds file.",
    )
    mask_positions = models.TextField(null=True, blank=True, default=None)

    template = models.TextField(default="", null=True, blank=True)
    ignore_warnings = models.BooleanField(
        default=False,
        help_text="Ignore warnings at validation",
    )

    def clean(self):
        if str(self.steam_id) in MOD_WARNINGS and not self.ignore_warnings:
            text = MOD_WARNINGS[str(self.steam_id)]

            text = (
                text
                + ' To ignore this warning, check the option "ignore warnings" at the bottom of this form.'
            )
            raise ValidationError(text)
        if self.type != ComponentType.VEHICLE and self.update:
            raise ValidationError("Only vehicle components can get an Update.ini file")

    def save(self, *args, **kwargs):
        # needles = ["number", "name", "description"]
        root_path = join(MEDIA_ROOT, "templates")
        if not exists(root_path):
            mkdir(root_path)
        template_path = join(
            root_path,
            self.component_name + ".veh",
        )
        if (
            self.type == ComponentType.VEHICLE
            and not self.template
            and exists(template_path)
        ):
            unlink(template_path)
        if self.type == ComponentType.VEHICLE and self.template:

            replacementMap = {
                "DefaultLivery": self.short_name + "_{number}.dds",
                "Number": "{number}",
                "Team": "{name}",
                "Description": "{description}",
                "FullTeamName": "{description}",
                "PitGroup": "Group{pitgroup}",
            }
            templateLines = self.template.split("\n")
            newLines = []
            for line in templateLines:
                hadReplacement = False
                for key, value in replacementMap.items():
                    pattern = rf'({key}\s{0,}=\s{0,}"?([^"^\n^\r]+)"?)'
                    matches = re.match(pattern, line, re.MULTILINE)
                    replacement = "{}={}\n".format(key, value)
                    if matches:
                        fullMatch = matches.groups(0)[0]
                        if '"' in fullMatch:
                            replacement = '{}="{}"\n'.format(key, value)

                        newLines.append(replacement)
                        hadReplacement = True
                if not hadReplacement:
                    newLines.append(line)

            self.template = "".join(newLines)
            # paste parsed template
            with open(template_path, "w") as file:
                file.write(self.template)
        super(Component, self).save(*args, **kwargs)

    def __str__(self):
        base_str = ""
        if self.alternative_name:
            base_str = "[" + self.alternative_name + "] "
        if self.base_component:
            return base_str + "{} (updates {})".format(
                self.component_name, self.base_component.steam_id
            )
        return base_str + self.component_name


class RaceSessions(models.Model):
    class Meta:
        verbose_name_plural = "Race sessions"

    description = models.CharField(default="Add description", max_length=200)
    type = models.CharField(
        max_length=2, choices=RaceSessionsType.choices, default=RaceSessionsType.TD
    )
    laps = models.IntegerField(default=0, help_text="Target laps of the session")
    real_road_time_scale = models.CharField(
        max_length=10,
        choices=RaceSessionGripScale.choices,
        default=RaceSessionGripScale.N,
    )

    grip = models.FileField(
        upload_to=get_conditions_file_root, blank=True, null=True, default=None
    )
    grip_needle = models.CharField(
        default=None,
        null=True,
        blank=True,
        max_length=100,
        help_text="If you want to use the mod provided grip, add a filename/ and or part of the rrbin filename. You can also add 'autosave' to use the autosave file, which must be existing (also keep settings folder in the server options). If found, the uploaded grip file will be ignored. You can also use the constants 'natural' or 'green' to define grip levels",  # noqa: E501
    )
    start = models.TimeField(
        blank=True,
        default=None,
        null=True,
        help_text="Target laps for this session. This is in-game time. If empty, the defaults will be used.",
    )
    length = models.IntegerField(
        default=0, help_text="Target length of the session in minutes"
    )
    weather = models.TextField(blank=True, null=True, default=None)
    track = models.ForeignKey("Track", on_delete=models.CASCADE, blank=True, null=True)
    race_finish_criteria = models.CharField(
        max_length=3,
        choices=RaceSessionFinishType.choices,
        default=None,
        blank=True,
        null=True,
    )

    def clean(self):
        if "R" not in str(self.type) and self.race_finish_criteria:
            raise ValidationError("This is only needed for a race session")
        if self.length < 0 or self.laps < 0:
            raise ValidationError(
                "Either length or laps is negative. Set to 0 to ignore."
            )
        if "P" in str(self.type) and self.laps > 0:
            raise ValidationError(
                "A practice can only have a time lenght. Set to 0 to ignore."
            )

        if "WU" in str(self.type) and self.laps > 0:
            raise ValidationError(
                "A warmup can only have a time lenght. Set to 0 to ignore."
            )

        if self.grip_needle and self.grip:
            raise ValidationError(
                "Grip and grip needle cannot be used at the same time"
            )

    def __str__(self):
        str = "[{}] {}, {} minutes, {} laps".format(
            self.type, self.description, self.length, self.laps
        )

        if self.track:
            str = str + f" [{self.track}]"

        if self.grip:
            str = str + ", gripfile: {}".format(basename(self.grip.name))

        if self.grip_needle:
            str = str + ", preset grip: {}".format(self.grip_needle)

        if self.grip or self.grip_needle:
            str = str + " " + self.real_road_time_scale + "x grip"

        if self.start:
            return str + ", start: {}".format(self.start)

        else:
            return str


class RaceConditions(models.Model):
    class Meta:
        verbose_name = "Race weekend"

    description = models.CharField(default="Add description", max_length=200)
    rfm = models.FileField(
        upload_to=get_conditions_file_root,
        storage=OverwriteStorage,
        blank=True,
        null=True,
        default=None,
        verbose_name="Alternative rFm file",
        help_text="An rFm file to overwrite standards, speeds, pit boxes etc.",
    )

    sessions = models.ManyToManyField(RaceSessions, blank=True)

    def __str__(self):
        sessions = self.sessions.all()
        sessions_list = []
        for session in sessions:
            sessions_list.append(
                "{}@{} [{} minutes/{} laps]".format(
                    session.type,
                    session.start if session.start is not None else "Default startime",
                    session.length,
                    session.laps,
                )
            )
        return "{} ({})".format(
            self.description, "No sessions" if len(sessions) == 0 else sessions_list
        )


class Track(models.Model):
    component = models.ForeignKey(Component, on_delete=models.CASCADE)
    layout = models.CharField(default="", blank=False, max_length=200)

    lon = models.FloatField(
        default=None, blank=True, null=True, verbose_name="Longitute"
    )
    lat = models.FloatField(
        default=None, blank=True, null=True, verbose_name="Latitute"
    )
    section_list = models.TextField(
        blank=True, default=None, null=True, verbose_name="Track sections"
    )

    def __str__(self):
        return "{}@{}".format(self.layout, self.component)

    def clean(self):
        if self.section_list:
            # check if sections and points are valid
            lines = self.section_list.split(linesep)
            for line in lines:
                parts = line.split(";")
                if len(parts) < 2 or len(parts) > 3:
                    raise ValidationError(f"The parts are not valid. {line}")


class Entry(models.Model):
    class Meta:
        verbose_name = "Livery"
        verbose_name_plural = "Liveries"

    component = models.ForeignKey(Component, on_delete=models.CASCADE)
    team_name = models.CharField(default="Example Team", max_length=200)
    vehicle_number = models.CharField(default="1", max_length=3)
    base_class = models.CharField(
        default=None,
        null=True,
        blank=True,
        max_length=200,
        help_text="On which class is the car based? If empty, APX will pick the first car as a basis. If the mod does not have multiple classes, you don't need this."  # noqa: E501
        if EASY_MODE
        else "If no component template is used, name the class of the car suitable to be used as a base. Otherwise the first veh file will be used.",
    )

    token = models.CharField(
        default=None, null=True, blank=True, max_length=100, unique=True
    )
    pit_group = models.IntegerField(
        default=1,
        help_text="The pit group for the entry. Stock tracks commonly using groups 1-30.",
    )
    additional_overwrites = models.TextField(
        blank=True,
        default=None,
        null=True,
        verbose_name="See Wiki article 'Wizard: Additional properties for entries' for details",
    )

    @property
    def events(self):
        events = Event.objects.filter(entries__in=[self.pk]).values_list(
            "name", flat=True
        )
        if len(events) == 0:
            return None
        return ", ".join(events)

    def clean(self):

        # validate additional overwrites, if needed
        # we assume the \r\n as the wizard
        if self.additional_overwrites:
            lines = self.additional_overwrites.split(linesep)
            pattern = r"^(.+)\s{0,}=\s{0,}\"(.+)\"$"
            for line in lines:
                got = match(pattern, line)
                if not got:
                    raise ValidationError(
                        'The value for the line "{}" does not follow the scheme Name="Value"!'.format(
                            line
                        )
                    )

    def __str__(self):
        return "[{}] {}#{}".format(self.component, self.team_name, self.vehicle_number)


class TrackFile(models.Model):
    file = models.FileField(
        upload_to=track_filename, storage=OverwriteStorage, max_length=500
    )

    track = models.ForeignKey(
        Track, on_delete=models.CASCADE, blank=False, null=False, default=None
    )

    def __str__(self):
        return str(self.track) + ": " + str(self.file)


class EntryFile(models.Model):
    file = models.FileField(
        upload_to=livery_filename, storage=OverwriteStorage, max_length=500
    )
    entry = models.ForeignKey(
        Entry, on_delete=models.CASCADE, blank=False, null=False, default=None
    )

    mask_added = models.BooleanField(
        default=False,
        help_text="Will be checked if a set of numberpaltes/ livery masks were added. Uncheck to force update.",
    )

    def __str__(self):
        return str(self.entry)

    def filename(self):
        return basename(self.file.name)

    def save(self, *args, **kwargs):
        needle = "{}_{}.dds".format(
            self.entry.component.short_name, self.entry.vehicle_number
        )

        regionNeedle = "{}_{}_Region.dds".format(
            self.entry.component.short_name, self.entry.vehicle_number
        )

        has_mask = (
            self.entry.component.update
            and self.entry.component.numberplate_template_r
            and self.entry.component.numberplate_template_mask_r
            and self.entry.component.numberplate_template_l
            and self.entry.component.numberplate_template_mask_l
        )

        if (
            (str(self.file).endswith(needle) or str(self.file).endswith(regionNeedle))
            and has_mask
            and not self.mask_added
            and self.pk
            and USE_WAND
        ):
            # attempt numberplate addition
            livery_path = join(MEDIA_ROOT, str(self.file))

            # add the livery mask on top of thel ivery
            livery = image.Image(filename=livery_path, format="raw")
            livery.compression = "dxt5"

            is_region = livery_path.endswith("_Region.dds")

            numberplate_template_path_r = (
                self.entry.component.numberplate_template_r
                if not is_region
                else self.entry.component.numberplate_template_mask_r
            )

            numberplate_template_r = image.Image(
                filename=join(MEDIA_ROOT, str(numberplate_template_path_r)),
                format="raw",
            )

            numberplate_template_path_l = (
                self.entry.component.numberplate_template_l
                if not is_region
                else self.entry.component.numberplate_template_mask_l
            )

            numberplate_template_l = image.Image(
                filename=join(MEDIA_ROOT, str(numberplate_template_path_l)),
                format="raw",
            )

            numberplate_template_r.compression = "dxt5"
            numberplate_template_l.compression = "dxt5"
            numberplates = json.loads(self.entry.component.mask_positions)
            if numberplates is not None:
                for numberplate in numberplates:
                    side = numberplate["side"]
                    template = (
                        numberplate_template_l
                        if side.lower() == "l"
                        else numberplate_template_r
                    )
                    with template.clone() as rotate:
                        outer = numberplate["outer"]
                        inner = numberplate["inner"]
                        rotation = numberplate["rotate"]
                        color_id = numberplate["color"]
                        size = numberplate["size"]
                        flop = numberplate["flop"]
                        if flop:
                            rotate.flop()
                        if not is_region:
                            with Drawing() as draw:
                                color = Color(color_id)
                                draw.fill_color = color
                                draw.font_size = size
                                draw.color = color
                                draw.text(inner[0], inner[1], self.entry.vehicle_number)
                                draw(rotate)
                        if rotation > 0:
                            rotate.rotate(rotation, None)
                        livery.composite(rotate, left=outer[0], top=outer[1])

            livery.save(filename=livery_path)
            self.mask_added = True

        super(EntryFile, self).save(*args, **kwargs)


@receiver(models.signals.post_delete, sender=EntryFile)
def auto_delete_file_on_delete(sender, instance, **kwargs):
    """
    Deletes file from filesystem
    when corresponding `MediaFile` object is deleted.
    """
    if instance.file:
        if isfile(instance.file.path):
            remove(instance.file.path)


# 0 Standing
# 1 formation lap & standing start
# 2 lap behind safety car & rolling start
# 4 fast rolling start


class EvenStartType(models.TextChoices):
    S = "0", "Standing start"
    FLS = "1", "Formation Lap and standing start"
    SCR = "2", "Lap behind safety car & rolling start"
    FR = "4", "Fast rolling start"


class ServerPlugin(models.Model):
    plugin_file = models.FileField(
        upload_to=get_plugin_root_path,
        help_text="The plugin file",
        blank=False,
        default=None,
        null=False,
    )

    plugin_path = models.CharField(
        blank=True,
        max_length=500,
        default=None,
        null=True,
        help_text="The target folder the file should be placed into. Seen relative from the rFactor 2 server root folder",
    )

    name = models.CharField(
        blank=True,
        max_length=500,
        default="",
        null=True,
        help_text="A organistory name for the plugin",
    )

    overwrites = models.TextField(
        default="{}",
        help_text="Additional JSON settings to use. ' Enabled: 1' will be added automatically.",
    )

    def __str__(self):
        return "{}: {}".format(self.name, basename(str(self.plugin_file)))

    def clean(self):
        try:
            json.loads(self.overwrites)
        except JSONDecodeError as e:
            raise ValidationError(f"This JSON is not valid. Reason: {str(e)}")

        if ".dll" not in self.plugin_file.path.lower() and self.overwrites != "{}":
            raise ValidationError("The overwrites are only valid for DLL files.")


class EventRejoinRules(models.TextChoices):
    N = "0", "No rejoin"
    F = "1", "yes with fresh vehicle"
    S = "2", "yes with vehicle in same physical condition"
    SI = "3", "yes including setup"


class EventFlagRules(models.TextChoices):
    N = "0", "None"
    P = "1", "Penalties only"
    PFC = "2", "Penalties & full-course yellows"
    EDQ = "3", "Everything except DQs"


# NOTE: https://github.com/scipy/scipy/issues/8389
class QualyMode(models.TextChoices):
    A = "0", "all cars qualify visibly on track together"
    O = "1", "only one car is visible at a time"  # noqa: #741
    R = "2", "use default from RFM, season, or track entry"


class WeatherAPI(models.TextChoices):
    OpenWeatherMap = "OpenWeatherMap", "OpenWeatherMap"
    DarkSky = "DarkSky", "DarkSky"
    ClimaCell = "ClimaCell", "ClimaCell"
    ClimaCell_V4 = "ClimaCell_V4", "ClimaCell_V4"


class BlueFlags(models.TextChoices):
    N = "0", "None"
    S = "1", "show but never penalize"
    P_0_3 = "2", "show and penalize if following within 0.3 seconds"
    P_0_5 = "3", "show and penalize if following within 0.5 seconds"
    P_0_7 = "4", "show and penalize if following within 0.7 seconds"
    P_0_9 = "5", "show and penalize if following within 0.7 seconds"
    P_1_1 = "6", "show and penalize if following within 1.1 seconds"
    R = "7", "Use rFm value"


class EventFailureRates(models.TextChoices):
    N = "0", "None"
    NOR = "1", "Normal"
    TS = "2", "Timescaled"


class QualyJoinMode(models.TextChoices):
    O = "0", "Open to all"  # noqa: #741
    P = "1", "Open but drivers will be pending an open session"
    C = "2", "closed"


class ParcFermeMode(models.TextChoices):
    O = "0", "Off"  # noqa: #741
    P = (
        "1",
        "no setup changes allowed between qual and race except for 'Free Settings')",
    )
    R = "2", "same unless rain"
    D = "3", "use RFM default"


class EventRaceTimeScale(models.TextChoices):
    P = "-1", "Race %"
    N = "0", "None"
    R = "1", "Normal"
    F2 = "2", "x2"
    F3 = "3", "x3"
    F4 = "4", "x4"
    F5 = "5", "x5"
    F10 = "10", "x10"
    F15 = "15", "x15"
    F20 = "20", "x20"
    F25 = "25", "x25"
    F30 = "30", "x30"
    F45 = "45", "x45"
    F60 = "60", "x60"


# 0=no restrictions on driving view, 1=cockpit\/tv cockpit\/nosecam only, 2=cockpit\/nosecam only, 3=cockpit only, 4=tracksides, 5=tracksides group 1",
class ForcedDrivingViewMode(models.TextChoices):
    N = "0", "no restrictions on driving view"
    C = "1", "cockpit/tv cockpit/nosecam only"
    CO = "3", "cockpit only"
    TO = "4", "tracksides"
    TOG1 = "5", "tracksides group 1"


class VersionOverwritePolicy(models.TextChoices):
    N = (
        "0",
        "Use the versions as user provided: If more than 1 version, use latest even version if updates are needed and the latest if not.",
    )
    G = (
        "1",
        "Try to guess versions: If base mod is encrypted, use this version for updates, else use the latest version.",
    )
    GT = (
        "2",
        "Same as second option, but use the scheme also for mods without an encrypted base mod",
    )


class Event(models.Model):
    name = models.CharField(
        default="",
        max_length=26,
        help_text="The Name of the event. Will be used as Race name in the server.",
        validators=[event_name_validator],
    )
    conditions = models.ForeignKey(
        RaceConditions,
        on_delete=models.CASCADE,
        verbose_name="race weekend",
        help_text="Conditions is a bundle of session definitions, containing session lengths and grip information.",
    )
    entries = models.ManyToManyField(Entry, blank=True, verbose_name="Liveries")
    tracks = models.ManyToManyField(Track)
    signup_active = models.BooleanField(default=False)
    signup_components = models.ManyToManyField(
        Component,
        verbose_name="Cars",
        blank=True,
        help_text="Cars allowed to be used. If no entries are existing, all available entries from the mod will be used.",
    )

    include_stock_skins = models.BooleanField(
        default=False,
        help_text="Attempt to add stock skins even if own liveries are used.",
    )
    start_type = models.CharField(
        max_length=3, choices=EvenStartType.choices, default=EvenStartType.S
    )

    real_weather = models.BooleanField(
        default=False,
        help_text="Decides if real weather should be used. This will be using https://forum.studio-397.com/index.php?threads/weatherplugin.58614/ in the background.",  # noqa: E501
    )
    weather_api = models.CharField(
        max_length=20,
        choices=WeatherAPI.choices,
        blank=True,
        null=True,
        default=None,
        help_text="The Weather API to use",
        verbose_name="Weather API",
    )
    weather_key = models.CharField(
        blank=True,
        null=True,
        default=None,
        max_length=255,
        help_text="The key to use for the weather API.",
    )

    temp_offset = models.IntegerField(
        default=0,
        help_text="Adds a positive or negative number to the temperature in Celsius.",
    )

    mod_name = models.CharField(
        default="",
        blank=True,
        max_length=50,
        help_text="Name of the mod to install. If no value is given, the scheme apx_{randomstring} will be used. Max length is 50 chars.",
        validators=[alphanumeric_validator],
    )

    mod_version = models.CharField(
        default=None,
        null=True,
        blank=True,
        max_length=50,
        help_text="Version suffix to be used for content updates (track, cars). If not set, the value '.9apx' will be used.",
        validators=[alphanumeric_validator_dots],
    )

    event_mod_version = models.CharField(
        default="",
        blank=True,
        max_length=50,
        help_text="Version suffix to be used for the mod itself. If not set, a RANDOM value in concatenation with '1.0+{random}' will be used.",
        validators=[alphanumeric_validator_dots],
    )

    deny_votings = models.BooleanField(
        default=False, help_text="Deny all admin functionalities for non-admins"
    )

    deny_session_voting = models.BooleanField(
        default=False, help_text="Disable any voting to switch sessions"
    )

    deny_ai_voting = models.BooleanField(
        default=False, help_text="Disable any voting to add AI cars"
    )

    deny_other_voting = models.BooleanField(
        default=False, help_text="Disable any other voting"
    )

    plugins = models.ManyToManyField(ServerPlugin, blank=True)

    timing_classes = models.TextField(
        default="{}",
        blank=True,
        help_text="JSON Config to rename classes, if needed",
    )
    welcome_message = models.TextField(
        default=None,
        null=True,
        blank=True,
        help_text="Welcome message. You can insert the driver name with the placeholder {driver_name}",
    )

    """

    Session options

    """

    damage = models.IntegerField(
        default=100,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Damage multiplier",
    )

    ai_strength = models.IntegerField(
        default=100,
        validators=[MinValueValidator(0), MaxValueValidator(120)],
        help_text="AI Driver Strength",
    )

    password = models.CharField(
        default="",
        blank=True,
        max_length=50,
        help_text="Join password. Has max length of 50 chars.",
    )

    admin_password = models.CharField(
        default="apx",
        blank=False,
        null=False,
        max_length=50,
        help_text="Admin password. Has max length of 50 chars. Cannot be empty",
    )

    rejoin = models.CharField(
        max_length=50,
        choices=EventRejoinRules.choices,
        default=EventRejoinRules.N,
        blank=False,
        null=False,
        help_text="Race rejoin ruling",
    )

    forced_driving_view = models.CharField(
        max_length=50,
        choices=ForcedDrivingViewMode.choices,
        default=ForcedDrivingViewMode.N,
        blank=False,
        null=False,
        help_text="Enforce a certain view for clients",
    )

    rules = models.CharField(
        max_length=50,
        choices=EventFlagRules.choices,
        default=EventFlagRules.N,
        blank=False,
        null=False,
        help_text="Race rules",
    )

    race_multiplier = models.CharField(
        max_length=50,
        choices=EventRaceTimeScale.choices,
        default=EventRaceTimeScale.R,
        blank=False,
        null=False,
        help_text="Race time scale",
        verbose_name="Race time scale",
    )

    fuel_multiplier = models.IntegerField(
        default=1,
        validators=[MinValueValidator(0), MaxValueValidator(7)],
        help_text="Fuel usage multiplier, use 0 to disable completely",
    )

    tire_multiplier = models.IntegerField(
        default=1,
        validators=[MinValueValidator(0), MaxValueValidator(7)],
        help_text="Tire usage multiplier, use 0 to disable completely",
    )

    failures = models.CharField(
        max_length=50,
        choices=EventFailureRates.choices,
        default=EventFailureRates.N,
        blank=False,
        null=False,
        help_text="Mechanical failure rates",
    )

    clients = models.IntegerField(
        default=20,
        validators=[MinValueValidator(10), MaxValueValidator(109)],
        help_text="Allowed clients",
    )

    ai_clients = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(109)],
        help_text="Allowed AI clients",
    )

    real_name = models.BooleanField(
        default=False,
        help_text="Decides if the server forces the client to expose the real name",
    )

    downstream = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(1000000)],
        help_text="Downstream in KBPS. Calculate with 2000 per client.",
    )

    upstream = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(1000000)],
        help_text="Upstream in KBPS. Calculate with 2000 per client.",
    )

    replays = models.BooleanField(
        default=False,
        help_text="Enable or disable replays for this event",
    )

    """
        Allowed driving aids
    """

    allow_traction_control = models.IntegerField(
        default=3,
        validators=[MinValueValidator(0), MaxValueValidator(3)],
        help_text="Allow traction control",
    )

    allow_anti_lock_brakes = models.IntegerField(
        default=2,
        validators=[MinValueValidator(0), MaxValueValidator(2)],
        help_text="Allow Anti-Lock Braking",
    )

    allow_stability_control = models.IntegerField(
        default=2,
        validators=[MinValueValidator(0), MaxValueValidator(2)],
        help_text="Allow Stability Control",
    )

    allow_auto_shifting = models.IntegerField(
        default=2,
        validators=[MinValueValidator(0), MaxValueValidator(3)],
        help_text="Allow Stability Control",
    )

    allow_steering_help = models.IntegerField(
        default=2,
        validators=[MinValueValidator(0), MaxValueValidator(3)],
        help_text="Allow steering help",
    )

    allow_braking_help = models.IntegerField(
        default=2,
        validators=[MinValueValidator(0), MaxValueValidator(2)],
        help_text="Allow braking help",
    )

    allow_auto_clutch = models.BooleanField(
        default=True,
        help_text="Allow auto clutch",
    )

    allow_invulnerability = models.BooleanField(
        default=False,
        help_text="Allow Invulnerability",
    )

    allow_auto_pit_stop = models.BooleanField(
        default=False,
        help_text="Allow auto pit stop",
    )

    allow_opposite_lock = models.BooleanField(
        default=False,
        help_text="Allow opposite lock",
    )

    allow_spin_recovery = models.BooleanField(
        default=False,
        help_text="Allow spin recovery",
    )

    allow_ai_toggle = models.BooleanField(
        default=False,
        help_text="Allow AI toggle",
    )

    cuts_allowed = models.IntegerField(
        default=2,
        validators=[MinValueValidator(0), MaxValueValidator(999999)],
        help_text="Track cuts allowed before a penalty is given",
    )

    qualy_mode = models.CharField(
        max_length=50,
        choices=QualyMode.choices,
        default=QualyMode.R,
        blank=False,
        null=False,
        help_text="Qualy mode",
    )

    blue_flag_mode = models.CharField(
        max_length=50,
        choices=BlueFlags.choices,
        default=BlueFlags.S,
        blank=False,
        null=False,
        help_text="Blue flag mode",
    )

    pause_while_zero_players = models.BooleanField(
        default=False,
        help_text="Pause while zero players",
    )

    pit_speed_override = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text="pitlane speed limit override in meters/sec (0=disabled)",
    )

    must_be_stopped = models.BooleanField(
        default=False,
        help_text="Whether drivers must come to a complete stop before exiting back to the monitor",
    )

    qualy_join_mode = models.CharField(
        max_length=50,
        choices=QualyJoinMode.choices,
        default=QualyJoinMode.O,
        blank=False,
        null=False,
        help_text="Closed Qualify Sessions",
    )

    after_race_delay = models.IntegerField(
        default=90,
        validators=[MinValueValidator(0)],
        help_text="Dedicated server additional delay (added to delay between sessions before loading next track",
    )

    delay_between_sessions = models.IntegerField(
        default=30,
        validators=[MinValueValidator(0)],
        help_text="Dedicated server delay before switching sessions automatically (after hotlaps are completed, if option is enabled), previously hardcoded to 45",  # noqa: E501
    )

    collision_fade_threshold = models.FloatField(
        default=0.7,
        help_text="Collision impacts are reduced to zero at this latency",
    )

    reconaissance_laps = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(1000000)],
        help_text="Reconnaissance laps",
    )

    skip_all_session_unless_configured = models.BooleanField(
        default=False,
        help_text="Instead of using default values from the player.JSON/ multiplayer.JSON, skip all sessions unless the ones configured with the conditions pack in APX.",  # noqa: E501
    )

    parc_ferme = models.CharField(
        max_length=50,
        choices=ParcFermeMode.choices,
        default=ParcFermeMode.D,
        blank=False,
        null=False,
        help_text="Parc Ferme ruling. If enforced, add values for the Free Settings field aswell",
    )

    free_settings = models.IntegerField(
        default=-1,
        validators=[MinValueValidator(-1), MaxValueValidator(1000000)],
        help_text="Use only if Parc Ferme is used: -1=use RFM/season/GDB default, or add to allow minor changes with fixed/parc ferme setups: 1=steering lock, 2=brake pressure, 4=starting fuel, 8=fuel strategy 16=tire compound, 32=brake bias, 64=front wing, 128=engine settings",  # noqa: E501
    )

    enable_auto_downloads = models.BooleanField(
        default=True,
        help_text="Whether to allow clients to autodownload files that they are missing.",
    )

    force_versions = models.CharField(
        max_length=10,
        choices=VersionOverwritePolicy.choices,
        default=VersionOverwritePolicy.N,
        blank=False,
        null=False,
        help_text="Versioning scheme",
    )

    player_overwrites = models.TextField(
        default="{}",
        help_text="Additional player.JSON overwrites (values here will get a priority, don't leave trailing commas).",
        blank=True,
        verbose_name="Player.JSON overwrites",
    )

    multiplayer_overwrites = models.TextField(
        default="{}",
        help_text="Additional multiplayer.JSON overwrites (values here will get a priority, don't leave trailing commas).",
        blank=True,
        verbose_name="Multiplayer.JSON overwrites",
    )

    def get_multiplayer_json_dict(self):
        # TODO: why OrderedDict?
        blob = OrderedDict()
        blob["Multiplayer Server Options"] = OrderedDict()
        blob["Multiplayer Server Options"]["Join Password"] = self.password
        blob["Multiplayer Server Options"]["Admin Password"] = self.admin_password
        blob["Multiplayer Server Options"]["Race Rejoin"] = int(self.rejoin)
        blob["Multiplayer Server Options"]["Max MP Players"] = self.clients
        blob["Multiplayer Server Options"]["Maximum AI"] = self.ai_clients
        if self.clients > 50:
            blob["Multiplayer Server Options"]["Lessen Restrictions"] = True
        blob["Multiplayer Server Options"]["Enforce Real Name"] = self.real_name
        blob["Multiplayer Server Options"]["Default Game Name"] = (
            "[APX] {}".format(self.name[0:20]) if ADD_PREFIX else self.name
        )

        # control aids
        blob["Multiplayer Server Options"][
            "Allowed Traction Control"
        ] = self.allow_traction_control
        blob["Multiplayer Server Options"][
            "Allowed Antilock Brakes"
        ] = self.allow_anti_lock_brakes
        blob["Multiplayer Server Options"][
            "Allowed Stability Control"
        ] = self.allow_stability_control
        blob["Multiplayer Server Options"][
            "Allowed Auto Shift"
        ] = self.allow_auto_shifting
        blob["Multiplayer Server Options"][
            "Allowed Steering Help"
        ] = self.allow_steering_help
        blob["Multiplayer Server Options"][
            "Allowed Brake Help"
        ] = self.allow_braking_help
        blob["Multiplayer Server Options"][
            "Allowed Auto Clutch"
        ] = self.allow_auto_clutch
        blob["Multiplayer Server Options"][
            "Allowed Invulnerability"
        ] = self.allow_invulnerability
        blob["Multiplayer Server Options"][
            "Allowed Auto Pit"
        ] = self.allow_auto_pit_stop
        blob["Multiplayer Server Options"][
            "Allowed Opposite Lock"
        ] = self.allow_opposite_lock
        blob["Multiplayer Server Options"][
            "Allowed Spin Recovery"
        ] = self.allow_spin_recovery
        blob["Multiplayer Server Options"]["Allow AI Toggle"] = self.allow_ai_toggle

        blob["Multiplayer General Options"] = OrderedDict()
        blob["Multiplayer General Options"]["Download Custom Skins"] = False
        blob["Multiplayer General Options"]["Net Connection Type"] = 6
        blob["Multiplayer General Options"]["Downstream Rated KBPS"] = self.downstream
        blob["Multiplayer General Options"]["Upstream Rated KBPS"] = self.upstream

        blob["Multiplayer Server Options"][
            "Pause While Zero Players"
        ] = self.pause_while_zero_players

        blob["Multiplayer Server Options"]["Must Be Stopped"] = self.must_be_stopped
        blob["Multiplayer Server Options"][
            "Closed Qualify Sessions"
        ] = self.qualy_join_mode
        blob["Multiplayer Server Options"]["Delay After Race"] = self.after_race_delay
        blob["Multiplayer Server Options"][
            "Delay Between Sessions"
        ] = self.delay_between_sessions
        blob["Multiplayer Server Options"][
            "Collision Fade Thresh"
        ] = self.collision_fade_threshold
        blob["Multiplayer Server Options"][
            "Pit Speed Override"
        ] = self.pit_speed_override
        blob["Multiplayer Server Options"][
            "Enable Autodownloads"
        ] = self.enable_auto_downloads

        if self.deny_votings:
            blob["Multiplayer Server Options"]["Admin Functionality"] = 0
        if self.deny_ai_voting:
            blob["Multiplayer Server Options"]["Vote Percentage Add AI"] = 100
        if self.deny_other_voting:
            blob["Multiplayer Server Options"]["Vote Percentage Other"] = 100
        if self.deny_session_voting:
            blob["Multiplayer Server Options"]["Vote Percentage Next Session"] = 100

        blob["Multiplayer Server Options"]["Forced Driving View"] = int(
            self.forced_driving_view
        )

        result = json.loads(json.dumps(blob))

        if self.multiplayer_overwrites != "{}":
            ow = json.loads(self.multiplayer_overwrites)
            result = merge_dicts(result, ow)

        return result

    def get_player_json_dict(self):
        # TODO: why OrderedDict?
        blob = OrderedDict()
        blob["Game Options"] = OrderedDict()
        blob["Game Options"]["MULTI Damage Multiplier"] = self.damage
        blob["Game Options"]["Record Replays"] = self.replays
        blob["Game Options"]["CURNT Fuel Consumption Multiplier"] = int(
            self.fuel_multiplier
        )
        blob["Game Options"]["GPRIX Fuel Consumption Multiplier"] = int(
            self.fuel_multiplier
        )
        blob["Game Options"]["MULTI Fuel Consumption Multiplier"] = int(
            self.fuel_multiplier
        )
        blob["Game Options"]["RPLAY Fuel Consumption Multiplier"] = int(
            self.fuel_multiplier
        )
        blob["Game Options"]["CHAMP Fuel Consumption Multiplier"] = int(
            self.fuel_multiplier
        )

        blob["Game Options"]["CURNT Tire Wear Multiplier"] = int(self.tire_multiplier)
        blob["Game Options"]["GPRIX Tire Wear Multiplier"] = int(self.tire_multiplier)
        blob["Game Options"]["MULTI Tire Wear Multiplier"] = int(self.tire_multiplier)
        blob["Game Options"]["RPLAY Tire Wear Multiplier"] = int(self.tire_multiplier)
        blob["Game Options"]["CHAMP Tire Wear Multiplier"] = int(self.tire_multiplier)

        blob["Game Options"]["Record Replays"] = self.replays

        blob["Race Conditions"] = OrderedDict()
        """
        if self.real_weather:
            blob["Race Conditions"]["MULTI Weather"] = 5
            blob["Race Conditions"]["GPRIX Weather"] = 5
        """
        blob["Race Conditions"]["MULTI Flag Rules"] = int(self.rules)
        blob["Race Conditions"]["RPLAY Flag Rules"] = int(self.rules)
        blob["Race Conditions"]["CHAMP Flag Rules"] = int(self.rules)
        blob["Race Conditions"]["CURNT Flag Rules"] = int(self.rules)
        blob["Race Conditions"]["GPRIX Flag Rules"] = int(self.rules)

        blob["Race Conditions"]["MULTI RaceTimeScale"] = int(self.race_multiplier)
        blob["Race Conditions"]["RPLAY RaceTimeScale"] = int(self.race_multiplier)
        blob["Race Conditions"]["CHAMP RaceTimeScale"] = int(self.race_multiplier)
        blob["Race Conditions"]["CURNT RaceTimeScale"] = int(self.race_multiplier)
        blob["Race Conditions"]["GPRIX RaceTimeScale"] = int(self.race_multiplier)

        blob["Race Conditions"]["MULTI Track Cuts Allowed"] = int(self.cuts_allowed)
        blob["Race Conditions"]["RPLAY Track Cuts Allowed"] = int(self.cuts_allowed)
        blob["Race Conditions"]["CHAMP Track Cuts Allowed"] = int(self.cuts_allowed)
        blob["Race Conditions"]["CURNT Track Cuts Allowed"] = int(self.cuts_allowed)
        blob["Race Conditions"]["GPRIX Track Cuts Allowed"] = int(self.cuts_allowed)

        blob["Race Conditions"]["MULTI PrivateQualifying"] = int(self.qualy_mode)
        blob["Race Conditions"]["RPLAY PrivateQualifying"] = int(self.qualy_mode)
        blob["Race Conditions"]["CHAMP PrivateQualifying"] = int(self.qualy_mode)
        blob["Race Conditions"]["CURNT PrivateQualifying"] = int(self.qualy_mode)
        blob["Race Conditions"]["GPRIX PrivateQualifying"] = int(self.qualy_mode)

        blob["Race Conditions"]["MULTI BlueFlags"] = int(self.blue_flag_mode)
        blob["Race Conditions"]["RPLAY BlueFlags"] = int(self.blue_flag_mode)
        blob["Race Conditions"]["CHAMP BlueFlags"] = int(self.blue_flag_mode)
        blob["Race Conditions"]["CURNT BlueFlags"] = int(self.blue_flag_mode)
        blob["Race Conditions"]["GPRIX BlueFlags"] = int(self.blue_flag_mode)

        blob["Race Conditions"]["MULTI Reconnaissance"] = int(self.reconaissance_laps)
        blob["Race Conditions"]["RPLAY Reconnaissance"] = int(self.reconaissance_laps)
        blob["Race Conditions"]["CHAMP Reconnaissance"] = int(self.reconaissance_laps)
        blob["Race Conditions"]["CURNT Reconnaissance"] = int(self.reconaissance_laps)
        blob["Race Conditions"]["GPRIX Reconnaissance"] = int(self.reconaissance_laps)

        blob["Race Conditions"]["MULTI ParcFerme"] = int(self.parc_ferme)
        blob["Race Conditions"]["RPLAY ParcFerme"] = int(self.parc_ferme)
        blob["Race Conditions"]["CHAMP ParcFerme"] = int(self.parc_ferme)
        blob["Race Conditions"]["CURNT ParcFerme"] = int(self.parc_ferme)
        blob["Race Conditions"]["GPRIX ParcFerme"] = int(self.parc_ferme)

        blob["Race Conditions"]["MULTI FreeSettings"] = int(self.free_settings)
        blob["Race Conditions"]["RPLAY FreeSettings"] = int(self.free_settings)
        blob["Race Conditions"]["CHAMP FreeSettings"] = int(self.free_settings)
        blob["Race Conditions"]["CURNT FreeSettings"] = int(self.free_settings)
        blob["Race Conditions"]["GPRIX FreeSettings"] = int(self.free_settings)

        blob["Race Conditions"]["MULTI Formation Lap"] = int(self.start_type)
        blob["Race Conditions"]["RPLAY Formation Lap"] = int(self.start_type)
        blob["Race Conditions"]["CHAMP Formation Lap"] = int(self.start_type)
        blob["Race Conditions"]["CURNT Formation Lap"] = int(self.start_type)
        blob["Race Conditions"]["GPRIX Formation Lap"] = int(self.start_type)

        blob["Game Options"]["CURNT AI Driver Strength"] = int(self.ai_strength)
        blob["Game Options"]["GPRIX AI Driver Strength"] = int(self.ai_strength)
        blob["Game Options"]["MULTI AI Driver Strength"] = int(self.ai_strength)
        blob["Game Options"]["RPLAY AI Driver Strength"] = int(self.ai_strength)
        blob["Game Options"]["CHAMP AI Driver Strength"] = int(self.ai_strength)

        result = json.loads(json.dumps(blob))

        if self.player_overwrites != "{}":
            ow = json.loads(self.player_overwrites)
            result = merge_dicts(result, ow)

        return result

    def __str__(self):
        return "{}".format(self.name)

    def clean(self, *args, **kwargs):

        for ow_field in ["player_overwrites", "multiplayer_overwrites"]:

            ow_value = getattr(self, ow_field)

            if not ow_value:
                setattr(self, ow_field, "{}")

            elif ow_value != "{}":
                try:
                    json.loads(ow_value)
                except JSONDecodeError:
                    raise ValidationError(f'"{ow_field}" is not a valid JSON.')

        if (
            self.real_weather
            and not self.weather_api
            or self.real_weather
            and not self.weather_key
        ):
            raise ValidationError("Check your weather settings")

        if self.admin_password == "apx":
            raise ValidationError("Please set the admin password.")

        if self.upstream == 0 and self.downstream == 0:
            got = get_speedtest_result()
            if got is not None:
                self.upstream = int(got["upstream"] * 1000)
                self.downstream = int(got["downstream"] * 1000)
            else:
                raise ValidationError(
                    "Please set upstream or downstream according to your network connection"
                )

        if self.welcome_message:
            parts = self.welcome_message.split(linesep)
            for part in parts:
                if len(part) > 50:
                    raise ValidationError(
                        "Limit the line length of each line of the welcome text to 50!"
                    )


class ServerStatus(models.TextChoices):
    STARTREQUESTED = "S+", "Start"
    STOPREQUESTED = "R-", "Stop"
    DEPLOY = "D", "Update config and redeploy"
    DEPLOYFORCE = "D+F", "Update config and redeploy, force content re-installation"
    STEAMUPDATE = "U", "Update to latest version of Steam branch"
    RESTARTWEEKEND = "W", "Restart weekend"


class ServerBranch(models.TextChoices):
    RC = "release-candidate", "release-candidate"
    P = "public", "public"
    PR = "previous-release", "previous-release"
    V21 = "v1121", "v1121"
    V22 = "v1122", "v1122"
    OLD = "old-ui", "old-ui"


class Server(models.Model):

    webui_port = models.IntegerField(
        default=1025,
        validators=[MinValueValidator(1025), MaxValueValidator(65535)],
        help_text="Port for the webui_port. Must be unique on all managed servers",
    )

    sim_port = models.IntegerField(
        default=54297,
        validators=[MinValueValidator(1025), MaxValueValidator(65535)],
        help_text="Port for the Simulation. Must be unique on all managed servers",
    )

    http_port = models.IntegerField(
        default=64297,
        validators=[MinValueValidator(1025), MaxValueValidator(65535)],
        help_text="Port for the HTTP Server. Must be unique on all managed servers",
    )
    steamcmd_bandwidth = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(1000000)],
        help_text="Limit the bandwidth steamcmd may use. 0 means unlimited download. Value is kbit/s. Maximum is 1000000",
    )
    name = models.CharField(
        blank=True,
        max_length=500,
        default="",
        null=True,
        help_text="A organistory name for the server",
    )
    url = models.CharField(
        blank=False, max_length=500, default="", help_text="The URL to the APX reciever"
    )

    discord_url = models.CharField(
        blank=True,
        null=True,
        max_length=500,
        default="",
        help_text="An alternative webhook URL to be used instead of the DISCORD_WEBHOOK setting",
    )
    secret = models.CharField(
        blank=False,
        max_length=500,
        default="",
        help_text="The secret for the communication with the APX reciever",
    )
    public_secret = models.CharField(
        blank=True,
        max_length=500,
        default=get_random_string(20),
        help_text="The secret for the communication with the APX race control",
    )
    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        help_text="The event to deploy. Note: You can only change this if the server is not running.",
    )
    action = models.CharField(
        max_length=3,
        choices=ServerStatus.choices,
        blank=True,
        default="",
        help_text="Runs an activity on the server.",
        verbose_name="Pending action to submit",
    )
    branch = models.CharField(
        max_length=50,
        choices=ServerBranch.choices,
        default=ServerBranch.P,
        blank=False,
        null=False,
        help_text="Public steam branch",
    )
    server_key = models.FileField(
        upload_to=get_key_root_path,
        help_text="Keyfile of the server. Will be filled on save",
        blank=True,
        default=None,
        null=True,
    )
    server_unlock_key = models.FileField(
        upload_to=get_key_root_path,
        help_text="Unlock keyfile of the server, usually named ServerUnlock.bin, required to use paid content. The field will cleared after unlocking",
        blank=True,
        default=None,
        null=True,
    )
    heartbeat_only = models.BooleanField(
        default=True,
        help_text="Tells the reciever instance to only include status updates as ticker messages",
    )
    update_on_build = models.BooleanField(
        default=False,
        help_text="Decides if APX will call dedicated server update when refreshing the content",
    )
    update_weather_on_start = models.BooleanField(
        default=False,
        help_text="Decides if APX will update the weather data on start if real weather is enabled",
    )
    collect_results_replays = models.BooleanField(
        default=False,
        help_text="Decides if APX will allow the server to persist the result and replay files",
    )
    remove_cbash_shaders = models.BooleanField(
        default=False,
        help_text="Decides if APX will remove the content of the folders CBash and shaders. Use with caution.",
        verbose_name="remove Cbash and Shaders folder",
    )
    remove_settings = models.BooleanField(
        default=False,
        help_text="Decides if APX will remove the content of the settings folder. If you plan to rely on autosave grip files, do not check this option",
        verbose_name="remove settings folder",
    )
    remove_unused_mods = models.BooleanField(
        default=False,
        help_text="Decides if APX will remove workshop items downloaded within steamcmd, but not used for the deployment. ",
        verbose_name="remove unused workshop items",
    )
    session_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        default=None,
        help_text="APX Session Id",
    )

    ignore_start_hook = models.BooleanField(
        default=True,
        help_text="Don't fire the Discord messages when the server starts",
    )

    ignore_stop_hook = models.BooleanField(
        default=True,
        help_text="Don't fire the Discord messages when the server stops",
    )

    ignore_updates_hook = models.BooleanField(
        default=True,
        help_text="Don't fire the Discord messages when the server was updated",
    )

    @property
    def logfile(self):
        key = get_server_hash(self.url)
        path = join(MEDIA_ROOT, "logs", key, "reciever.log")
        contents = None
        if exists(path):
            with open(path, "r") as file:
                contents = file.read()
        return contents

    @property
    def is_created_by_apx(self):
        path = join(BASE_DIR, "server_children", self.public_secret)
        return exists(path)

    @property
    def firewall_rules(self):
        rules = ""

        name = self.public_secret
        for port in [self.sim_port, self.http_port]:
            rules = (
                rules
                + f'New-NetFirewallRule -DisplayName "APX RULE {name} ({port} TCP)" -Direction Inbound -LocalPort {port} -Protocol TCP -Action Allow\n'
            )
        for port in [self.sim_port, self.http_port + 1, self.http_port + 2]:
            rules = (
                rules
                + f'New-NetFirewallRule -DisplayName "APX RULE {name} ({port} UDP)" -Direction Inbound -LocalPort {port} -Protocol UDP -Action Allow\n'
            )
        return rules

    @property
    def ports(self):
        return "TCP: {}, {}/ UDP: {}, {}, {}".format(
            self.sim_port,
            self.http_port,
            self.sim_port,
            self.http_port + 1,
            self.http_port + 2,
        )

    @property
    def state_info(self):
        if not self.pk or self.pk not in state_map:
            return "-"
        return state_map[self.pk]

    @property
    def status_info(self):
        if not self.pk or self.pk not in status_map:
            return "-"
        status = status_map[self.pk]
        status = json.loads(status.replace("'", '"'))
        # no status to report (e. g. new server)
        response = '<img src="{}admin/img/icon-no.svg" alt="Not Running"> Server is not running</br>'.format(
            STATIC_URL
        )

        if not status:
            response = '<img src="{}admin/img/icon-no.svg" alt="Not Running"> Server did not return a status yet</br>'.format(
                STATIC_URL
            )
        elif status and status["in_deploy"] is True:
            response = '<img src="{}admin/img/icon-no.svg" alt="Not Running"> The server is deploying</br>'.format(
                STATIC_URL
            )
        elif status and status["running"] is False:
            response = '<img src="{}admin/img/icon-no.svg" alt="Not Running"> Server is not running</br>'.format(
                STATIC_URL
            )
        elif status and status["running"] is True:
            response = '<img src="{}admin/img/icon-yes.svg" alt="Running"> Server is running</br>'.format(
                STATIC_URL
            )
            try:
                for vehicle in status.get("vehicles", []):
                    vehicle_text = (
                        "[{}, Pit {}] {}: {} (SteamID:{}), penalties: {}".format(
                            vehicle["carClass"],
                            vehicle["pitGroup"],
                            vehicle["vehicleName"],
                            vehicle["driverName"],
                            vehicle["steamID"],
                            vehicle["penalties"],
                        )
                    )
                    response = response + vehicle_text + "</br>"
            except JSONDecodeError as e:
                logger.error(e, exc_info=1)
                response = str(e)
        return mark_safe(response)

    def __str__(self):
        return self.url if not self.name else self.name

    # TODO: too many checks here
    def clean(self):
        status = status_map[self.pk] if self.pk and self.pk in status_map else None
        if not self.server_key and self.action:
            raise ValidationError(
                "The server was not processed yet. Wait a short time until the key is present."
            )
        if status is not None and status["running"] is False and self.action == "R-":
            raise ValidationError("The server is not running")

        if status is not None and status["running"] is True and self.action == "D":
            raise ValidationError("Stop the server first")

        if status is not None and status["running"] is True and self.action == "S+":
            raise ValidationError("Stop the server first")

        if self.action == "D" and not self.event:
            raise ValidationError("You have to add an event before deploying")

        if status and status["in_deploy"] in True:
            raise ValidationError("Wait until deployment is over")

        if self.action == "W" and status and status["in_deploy"] is True:
            raise ValidationError("Wait until deployment is over")

        if self.action == "W" and status and status["running"] is False:
            raise ValidationError("Start the server first")

        if status is not None and status["running"] is False and self.action == "WU":
            raise ValidationError("Start the server first")

        if not str(self.url).endswith("/"):
            raise ValidationError("The server url must end with a slash!")

        if self.remove_unused_mods and USE_GLOBAL_STEAMCMD:
            raise ValidationError(
                "You use a global steamcmd installation. Enabling this option will cause servers to remove the content for other servers."
            )

        other_servers = Server.objects.exclude(pk=self.pk)
        occupied_ports_tcp = []
        occupied_ports_udp = []

        from urllib.parse import urlparse

        server_url_parts = urlparse(self.url)
        server_parts = server_url_parts.netloc.split(":")
        server_host = server_parts[0]

        for server in other_servers:
            # locate host
            url_parts = urlparse(server.url)
            parts = url_parts.netloc.split(":")
            host = parts[0]

            if host == server_host:
                occupied_ports_tcp.append(server.http_port)
                occupied_ports_tcp.append(server.webui_port)
                occupied_ports_udp.append(server.sim_port)

        if (
            self.http_port in occupied_ports_tcp
            or self.webui_port in occupied_ports_tcp
            or self.sim_port in occupied_ports_udp
        ):
            raise ValidationError(
                "The ports of this server are already taken. TCP ports taken: {}, UDP ports taken: {}".format(
                    occupied_ports_tcp, occupied_ports_tcp
                )
            )

        if MAX_SERVERS is not None:
            amount = Server.objects.count()
            if amount >= MAX_SERVERS:
                raise ValidationError(
                    "You exceeded the maximum amount of available servers. You are allowed to use {} server instances. You won't be able to deploy until you not exceed that limit anymore".format(  # noqa: E501
                        MAX_SERVERS
                    )
                )
        steamcmd_bandwidth = 0
        other_servers = Server.objects.all()
        for server in other_servers:
            if server.event:
                if self.pk != server.pk:
                    steamcmd_bandwidth = steamcmd_bandwidth + server.steamcmd_bandwidth

        steamcmd_bandwidth = steamcmd_bandwidth + self.steamcmd_bandwidth

        if MAX_STEAMCMD_BANDWIDTH is not None:
            if self.steamcmd_bandwidth == 0:
                raise ValidationError(
                    "Steamcmd bandwidth limits are enforced. Please set a limit for the steamcmd bandith. Available bandwidth: {} kbit/s".format(
                        MAX_STEAMCMD_BANDWIDTH - steamcmd_bandwidth
                    )
                )
            if steamcmd_bandwidth > MAX_STEAMCMD_BANDWIDTH:
                raise ValidationError(
                    "Steamcmd bandwidth limits are enforced. You exceeded the available bandwidth by {} kbit/s".format(
                        (MAX_STEAMCMD_BANDWIDTH - steamcmd_bandwidth) * -1
                    )
                )

        if self.event:
            upstream_sum = 0
            downstream_sum = 0
            other_servers = Server.objects.all()
            for server in other_servers:
                if server.event:
                    if self.pk != server.pk:
                        upstream_sum = upstream_sum + server.event.upstream
                        downstream_sum = downstream_sum + server.event.downstream

            upstream_sum = upstream_sum + self.event.upstream
            downstream_sum = downstream_sum + self.event.downstream
            if (
                MAX_DOWNSTREAM_BANDWIDTH is not None
                and MAX_DOWNSTREAM_BANDWIDTH <= downstream_sum
            ):
                raise ValidationError(
                    "You exceeded the maximum downstream bandwidth. You are allowed to use {} kbit/s, you requested {} kbit/s".format(
                        MAX_DOWNSTREAM_BANDWIDTH, downstream_sum
                    )
                )
            if (
                MAX_UPSTREAM_BANDWIDTH is not None
                and MAX_UPSTREAM_BANDWIDTH <= upstream_sum
            ):
                raise ValidationError(
                    "You exceeded the maximum upstream bandwidth. You are allowed to use {} kbit/s, you requested {} kbit/s".format(
                        MAX_UPSTREAM_BANDWIDTH, upstream_sum
                    )
                )
        if (
            self.action != ""
            or self.server_key is None
            or self.server_unlock_key is not None
        ):
            background_thread = Thread(
                target=background_action_server, args=(self,), daemon=True
            )
            background_thread.start()

        create_firewall_script(self)


def background_action_server(server):
    do_server_interaction(server)


@receiver(models.signals.pre_delete, sender=Server)
def remove_server_children(sender, instance, **kwargs):
    background_thread = Thread(
        target=remove_server_children_thread, args=(instance,), daemon=True
    )
    background_thread.start()


def remove_server_children_thread(instance):
    id = instance.public_secret
    server_children = join(BASE_DIR, "server_children", id)
    # lock the path to prevent the children management module to start stuff again
    lock_path = join(server_children, "delete.lock")
    # folder could be already removed
    if exists(server_children):
        with open(lock_path, "w") as file:
            file.write("bye")


def background_action_chat(chat):
    try:
        key = get_server_hash(chat.server.url)

        run_apx_command(key=key, cmd="chat", args=[chat.message])

        # OLD run_apx_command(key, "--cmd chat --args {} ".format(chat.message))
        chat.success = True
    except Exception as e:
        logger.error(e, exc_info=1)
        chat.success = False
    finally:
        chat.save()


@receiver(post_save, sender=Server)
def my_handler(sender, instance, **kwargs):
    create_virtual_config()


class Chat(models.Model):
    server = models.ForeignKey(Server, on_delete=models.CASCADE)
    message = models.TextField(
        blank=True,
        null=True,
        default=None,
        max_length=50,
        help_text="Submits a message or a command to the given server. Can't be longer than 50 chars",
    )
    success = models.BooleanField(default=False)
    date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return "{}@{}: {}".format(
            self.server, self.date.strftime("%m/%d/%Y, %H:%M:%S"), self.message
        )

    def clean(self):
        background_thread = Thread(
            target=background_action_chat, args=(self,), daemon=True
        )
        background_thread.start()


class ServerCron(models.Model):
    class Meta:
        verbose_name_plural = "Server schedules"
        verbose_name = "Server schedule"

    server = models.ForeignKey(
        Server, on_delete=models.CASCADE, blank=False, null=False, default=None
    )
    event = models.ForeignKey(
        Event, on_delete=models.CASCADE, blank=True, null=True, default=None
    )
    action = models.CharField(
        max_length=3,
        choices=ServerStatus.choices,
        blank=True,
        default="",
        help_text="Runs an activity on the server.",
        verbose_name="Pending action to submit",
    )
    start_time = models.TimeField(
        blank=True,
        default=None,
        null=True,
        help_text="The start time the job should start",
    )

    modifier = models.IntegerField(
        default=1,
        blank=False,
        null=False,
        help_text="Repeat the job each X minutes, a value of 1 means no repeat",
        verbose_name="Repeat",
    )

    disabled = models.BooleanField(
        default=False, blank=False, null=False, help_text="Disables the job"
    )

    end_time = models.TimeField(
        blank=True,
        default=None,
        null=True,
        help_text="The end time the job should start",
    )
    message = models.TextField(
        default=None,
        null=True,
        blank=True,
        help_text="Message to send",
    )

    apply_only_if_practice = models.BooleanField(default=False)

    def __str__(self):
        base_str = (
            '{} "{}"'.format(dict(ServerStatus.choices)[self.action], self.server)
            if self.action
            else 'Message "{}"'.format(self.server)
        )
        if self.event:
            base_str = '{} "{}" on "{}"'.format(
                dict(ServerStatus.choices)[self.action], self.event, self.server
            )
        if self.disabled:
            base_str = "Disabled: " + base_str
        if self.end_time:
            base_str = base_str + " from {} to {}".format(
                self.start_time, self.end_time
            )
        else:
            base_str = base_str + " at {}".format(self.start_time)
        if self.modifier > 1:
            base_str = base_str + ", repeat each {} minutes".format(self.modifier)

        return base_str

    def clean(self):
        if self.action != "D" and self.action != "D+F" and self.event:
            raise ValidationError(
                "The event is only needed when deploying new updates."
            )
        if self.modifier == 1 and self.end_time:
            raise ValidationError(
                "Yo only need an end time if the job should repeat multiple times per day"
            )
        if not self.server:
            raise ValidationError("Select a server first")
        if self.action == "D" and not self.event:
            raise ValidationError("You have to add an event before deploying")
        if self.message:
            parts = self.message.split(linesep)
            for part in parts:
                if len(part) > 50:
                    raise ValidationError(
                        "Limit the line length of each line of the text to 50!"
                    )


@receiver(models.signals.pre_delete, sender=ServerCron)
def remove_cron_from_windows(sender, instance, **kwargs):
    id = instance.pk
    task_name = f"apx_task_{id}"
    delete_command_line = f"schtasks /delete /tn {task_name} /f"
    logger.info(delete_command_line)
    system(delete_command_line)


@receiver(models.signals.post_save, sender=ServerCron)
def add_cron_to_windows(sender, instance, **kwargs):
    id = instance.pk
    task_name = f"apx_task_{id}"
    delete_command_line = f"schtasks /delete /tn {task_name} /f"
    logger.info(delete_command_line)
    system(delete_command_line)
    if not instance.disabled:
        python_path = (
            join(BASE_DIR, "python.exe")
            if exists(join(BASE_DIR, "python.exe"))
            else "python.exe"
        )

        # today = datetime.today().strftime("%Y-%m-%d")
        schedule_part = ""
        start_time = instance.start_time
        end_time = instance.end_time
        modifier = instance.modifier
        schedule_part = "DAILY"
        if modifier > 1:
            start_str = str(start_time).split(":")

            start_hours = int(start_str[0])
            start_minutes = int(start_str[1])

            end_hours = 24
            end_minutes = 59
            if end_time:
                end_str = str(end_time).split(":")
                end_hours = int(end_str[0])
                end_minutes = int(end_str[1])

            diff_hours = end_hours - start_hours
            diff_minutes = end_minutes - start_minutes

            if diff_hours < 0:
                diff_hours = 24 + diff_hours

            if diff_minutes < 0:
                diff_minutes = 60 - start_minutes + end_minutes

            schedule_part = (
                schedule_part + f" /ri {modifier} /du {diff_hours}:{diff_minutes}"
            )
        # https://stackoverflow.com/questions/6814075/windows-start-b-command-problem#6814111
        run_command = (
            f"start /d '{BASE_DIR}' /b 'apx' '{python_path}' manage.py cron_run {id}"
        )
        command_line = f'schtasks /create /tn {task_name} /st {start_time} /sc {schedule_part} /tr "cmd /c {run_command}"'
        logger.info(command_line)
        system(command_line)


class TickerMessageType(models.TextChoices):
    PenaltyAdd = "P+", "PenaltyAdd"
    PenaltyRemove = "P-", "Penaltyrevoke"
    SlowCar = "V", "SlowCar"
    PitEntry = "PI", "PitEntry"
    PitExit = "PO", "PitExit"
    GarageEntry = "GI", "GarageEntry"
    GarageExit = "GO", "GarageExit"
    StatusChange = "S", "StatusChange"
    PositionChange = "P", "PositionChange"
    PositionChangeUnderYellow = "PY", "PositionChangeUnderYellow"
    BestLapChange = "PB", "BestLapChange"
    PitStatusChange = "PS", "PitStatusChange"
    Lag = "L", "Lag"
    LapsCompletedChange = "LC", "LapsCompletedChange"
    PittingStart = "PSS", "PittingStart"
    PittingEnd = "PSE", "PittingEnd"
    DriverSwap = "DS", "DriverSwap"
    VLow = "VL", "VLow"


class TickerMessage(models.Model):
    class Meta:
        verbose_name_plural = "Ticker messages"

    server = models.ForeignKey(
        Server, on_delete=models.CASCADE, blank=False, null=False, default=None
    )

    date = models.DateTimeField(auto_now_add=True)
    message = models.CharField(
        max_length=255,
        blank=False,
        null=False,
        default=None,
        help_text="Event description",
    )

    type = models.CharField(
        max_length=3,
        choices=TickerMessageType.choices,
        blank=True,
        default="",
        help_text="Type",
        verbose_name="Type",
    )

    event_time = models.IntegerField(default=0)
    session_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        default=None,
        help_text="APX Session Id",
    )
    session = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        default=None,
        help_text="In game session identifier",
    )

    def __str__(self):
        try:
            data = json.loads(self.message)
            if self.type == "P+":
                return "Penalty added for {}".format(data["driver"])

            if self.type == "P-":
                return "Penalty revoked for {}".format(data["driver"])

            if self.type == "V":
                return "Slow car: {}".format(data["driver"])

            if self.type == "PI":
                return "Pit entry {}".format(data["driver"])

            if self.type == "PO":
                return "Pit exit {}".format(data["driver"])

            if self.type == "GI":
                return "Garage entry {}".format(data["driver"])

            if self.type == "GO":
                return "Garage exit {}".format(data["driver"])

            if self.type == "S":
                return "Status change {} (was: {} is: {})".format(
                    data["driver"], data["old_status"], data["status"]
                )

            if self.type == "P":
                return "New position for {}: P{} ({:+})".format(
                    data["driver"], data["new_pos"], data["new_pos"] - data["old_pos"]
                )

            if self.type == "PY":
                return "New position (possibly under yellow) for {}: P{} ({:+})".format(
                    data["driver"],
                    data["new_pos"],
                    data["new_pos"] - data["old_pos"],
                )

            if self.type == "PB":
                return "New personal best for {}: {}".format(
                    data["driver"], data["new_best"]
                )

            if self.type == "DS":
                return "Driver Swap: {} out, {} in".format(
                    data["old_driver"], data["new_driver"]
                )

            if self.type == "PS":
                return "Pit status change for {}: {} (was {})".format(
                    data["driver"], data["status"], data["old_status"]
                )

            if self.type == "LC":
                return "Driver {} now completed {} laps".format(
                    data["driver"], data["laps"]
                )

            if self.type == "PSS":
                return "Pitting start for {}".format(data["driver"])

            if self.type == "PSE":
                return "Pitting end for {}".format(data["driver"])

            if self.type == "L":
                return "Lag suspect for {}, nearby: {}. Speed difference was {}".format(
                    data["driver"],
                    "".join(data["nearby"]) if len(data["nearby"]) else "Nobody",
                    data["old_speed"] - data["speed"],
                )

            if self.type == "VL":
                return "Low speed or stationary car {}, nearby {}".format(
                    data["driver"], data["nearby"]
                )
        except Exception as e:
            logger.error(e, exc_info=1)
            pass
        return self.type
