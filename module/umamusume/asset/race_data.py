import csv
import os.path

from bot.base.common import ImageMatchConfig
from bot.base.resource import Template
from module.umamusume.asset import REF_SUITABLE_RACE

RACE_TEMPLATE_MATCH_ACCURACY = 0.71

RACE_LIST: dict[int, list] = {}
UMAMUSUME_RACE_TEMPLATE_PATH = "/umamusume/race"

PERIOD_TO_RACES = {}
RACE_GRADE = {}


def _load_all_race_data():
    with open('resource/umamusume/data/race.csv', 'r', encoding="utf-8") as file:
        reader = csv.reader(file)
        for row in reader:
            if len(row) >= 6:
                race_id = int(row[1])
                race_name = row[3]
                grade = row[5].strip()
                time_period = int(row[0])

                path = "resource" + UMAMUSUME_RACE_TEMPLATE_PATH + "/" + str(race_id) + ".png"
                if os.path.isfile(path):
                    t = Template(
                        str(race_id),
                        UMAMUSUME_RACE_TEMPLATE_PATH,
                        ImageMatchConfig(match_accuracy=RACE_TEMPLATE_MATCH_ACCURACY),
                    )
                    race_info = (race_id, race_name, t)
                    RACE_LIST[race_id] = race_info

                if time_period not in PERIOD_TO_RACES:
                    PERIOD_TO_RACES[time_period] = []
                PERIOD_TO_RACES[time_period].append(race_id)

                if grade:
                    RACE_GRADE[race_id] = grade

    RACE_LIST[0] = (0, "suitable", REF_SUITABLE_RACE)


_load_all_race_data()


def get_races_for_period(time_period: int) -> list[int]:
    """Get all race IDs available for a specific time period"""
    return PERIOD_TO_RACES.get(time_period, [])


def is_g1_race(race_id):
    return RACE_GRADE.get(race_id, '') == 'G1'


def is_g2_race(race_id):
    return RACE_GRADE.get(race_id, '') == 'G2'


def is_g3_race(race_id):
    return RACE_GRADE.get(race_id, '') == 'G3'
