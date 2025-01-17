from django.core.management.base import BaseCommand
from django.db.models import Q
from os.path import exists, join
from os import mkdir, listdir
from wizard.settings import BASE_DIR, MEDIA_ROOT
from webgui.models import Component, Entry, EntryFile, TrackFile, Track
from webgui.util import FILE_NAME_SUFFIXES, FILE_NAME_SUFFIXES_MEANINGS
from shutil import copyfile
from re import search
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Import data"

    def get_file_meaning(self, filename):
        selected_suffix = None
        for index, suffix in enumerate(FILE_NAME_SUFFIXES):
            if str(filename).endswith(suffix):
                selected_suffix = FILE_NAME_SUFFIXES_MEANINGS[index]
                break
        return selected_suffix

    def get_vehicle_filename(
        self, filename, component_name, short_name, vehicle_number, full_path=True
    ):

        full_user_path = join(MEDIA_ROOT)
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
                break
        if selected_suffix is None:
            msg = f"We can't identify that file purpose: {filename}"
            logger.error(msg)
            raise Exception(msg)
        if "#" in vehicle_number:
            vehicle_number = vehicle_number.split("#")[1]
        if not full_path:
            return "{}_{}{}".format(short_name, vehicle_number, selected_suffix)
        new_file_path = join(
            "liveries",
            component_name,
            "{}_{}{}".format(short_name, vehicle_number, selected_suffix),
        )
        return new_file_path

    def handle(self, *args, **options):
        import_path = join(BASE_DIR, "import")
        if not exists(import_path):
            mkdir(import_path)
        short_name = input(
            "Name a valid short name, steam id or component name to identify the files: "
        )
        clear_old = (
            input(
                "Do you want to clear old entries referred to this component? Y/N: "
            ).lower()
            == "y"
        )
        entries = Component.objects.filter(Q(short_name=str(short_name)))
        if entries.count() == 0:
            entries = Component.objects.filter(Q(component_name=str(short_name)))
        if entries.count() == 0:
            entries = Component.objects.filter(Q(steam_id=int(short_name)))

        if entries.count() != 1:
            msg = f"Did not manage to find a component with key {short_name}."
            logger.error(msg)
            raise Exception(msg)
        else:
            entry = entries.first()
            logger.info(
                "We will use the component {} for this import".format(
                    entry.component_name
                )
            )
        is_vehicle = entries.first().type == "VEH"
        files = listdir(import_path)
        if not is_vehicle:
            layout = input("Name the layout: ")
            track = Track.objects.filter(
                component=entries.first(), layout=layout
            ).first()
            if track is None:
                msg = f"No track found with layout {layout}"
                logger.error(msg)
                raise Exception(msg)
            logger.info("Component {}, layout {}".format(entries.first(), layout))
            for file in files:
                logger.info(f"\t File {file}")

            confirm = input("Is this okay? Y/N: ")
            if confirm.lower() != "y":
                raise Exception("Abort.")
            if clear_old:
                TrackFile.objects.filter(track=track).delete()
            for file in files:
                track_file = TrackFile()
                track_file.track = track

                parent_path = join(
                    BASE_DIR,
                    "uploads",
                    "tracks",
                    track_file.track.component.component_name,
                )
                if not exists(parent_path):
                    mkdir(parent_path)
                relative_path = join(
                    "tracks", track_file.track.component.component_name, file
                )
                track_file.file = join(relative_path)
                source_path = join(BASE_DIR, "import", file)
                target_path = join(BASE_DIR, "uploads", relative_path)
                logger.info(f"Copied {file} to {target_path}")
                track_file.save()
                copyfile(source_path, target_path)

        if is_vehicle:
            regex_map = {
                "anum": r"(?P<number>[a-zA-Z]?\d+[a-zA-Z]?)",
                "num": r"(?P<number>\d+)",
            }
            got = input("Can entries be alphanumeric (e. g. '13x')? Y/N: ")

            pattern = regex_map["num"]
            if got.lower() == "y":
                pattern = regex_map["anum"]

            team_name = entries.first()

            # group files
            file_groups = {}
            unknown_files = []

            for file in files:
                matches = search(pattern, file)
                number = None
                if matches:
                    number = matches.group("number")
                if number is not None:
                    if number not in file_groups:
                        file_groups[number] = []
                    file_groups[number].append(file)
                else:
                    unknown_files.append(file)

            team_names_add = input("Do you want to set team names? Y/N: ")
            if team_names_add.lower() == "y":
                new_groups = {}
                for number, files in file_groups.items():
                    new_name = input(
                        f"Name of team with car #{number} (enter to omit): "
                    )
                    if new_name:
                        new_groups[f"{new_name}#{number}"] = files
                    else:
                        new_groups[number] = files
                file_groups = new_groups

            for number, files in file_groups.items():
                logger.info(f"Entry {number}:")
                for file in files:
                    new_name = self.get_vehicle_filename(
                        file,
                        entries.first().component_name,
                        entries.first().short_name,
                        number,
                        False,
                    )
                    if new_name != file:
                        logger.info(
                            f"\t File {file} => {new_name}: "
                            + "({})".format(self.get_file_meaning(file))
                        )
                    else:
                        logger.info(
                            f"\t File {file}: "
                            + "({})".format(self.get_file_meaning(file))
                        )
            logger.info(
                "Following files will be ignored (e. g. as it's a file not related to an entry or the file is not yet supported by APX)"
            )
            for file in unknown_files:
                logger.info(f"\t{file}")
            confirm = input("Is this okay? Y/N: ")

            if confirm.lower() == "y":
                if clear_old:
                    Entry.objects.filter(component=entries.first()).delete()
                    EntryFile.objects.filter(entry__component=entries.first()).delete()
                for number, files in file_groups.items():
                    logger.info(f"Processing matches for car {number}")
                    existing_entries = Entry.objects.filter(
                        component=entries.first(), vehicle_number=number
                    )
                    if existing_entries.count() == 1:
                        msg = "The entry is already existing for this component"
                        logger.error(msg)
                        raise Exception(msg)
                    e = Entry()
                    e.component = entries.first()
                    if "#" not in number:
                        e.team_name = team_name
                        e.vehicle_number = number
                    else:
                        parts = number.split("#")
                        e.team_name = parts[0]
                        e.vehicle_number = parts[1]
                    e.save()
                    for file in files:
                        logger.info(f"Adding file {file} to entry of car {number}")
                        e_f = EntryFile()
                        e_f.entry = e
                        source_path = join(BASE_DIR, "import", file)
                        file_name = self.get_vehicle_filename(
                            file,
                            e.component.component_name,
                            e.component.short_name,
                            number,
                        )
                        e_f.file = file_name
                        target_path = join(BASE_DIR, "uploads", file_name)
                        logger.info(f"Copied {file} to {target_path}")
                        e_f.save()
                        copyfile(source_path, target_path)
