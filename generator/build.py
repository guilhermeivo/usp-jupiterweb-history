from configparser import ConfigParser
from datetime import datetime, timezone
from pathlib import Path
import re
import unicodedata
import yaml
from jinja2 import Environment, FileSystemLoader
import graphviz

from config import SITE_PREFIX

ROOT = Path(".")
OUTPUT = Path("_site")

env = Environment(
    loader=FileSystemLoader("generator/templates"),
    trim_blocks=True,
    lstrip_blocks=True
)

course_template = env.get_template("course.html.j2")
index_template = env.get_template("index.html.j2")
departament_template = env.get_template("departament.html.j2")
css_template = env.get_template("alabaster.css.j2")


def load_courses():
    courses = []

    for yaml_file in ROOT.glob("*/*.yaml"):
        departament = yaml_file.parent.name

        with open(yaml_file, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        courses.append({
            "departament": departament,
            "file": yaml_file,
            "data": data
        })

    return courses


def normalize_code(code):
    return code.lower()


def find_nearest_course(courses, course, requirement):
    course_data = course["data"]
    best_course = None

    for course_search in courses:
        if normalize_code(requirement.get("code")) != normalize_code(course_search["file"].stem):
            continue

        if best_course is None:
            best_course = course_search
            continue

        best_date = best_course["data"].get("updated_at", "19700101000000")

        diff_date_a = best_date - course_data.get("updated_at", "19700101000000")
        diff_date_b = course_search["data"].get("updated_at", "19700101000000") - course_data.get("updated_at", "19700101000000")

        if diff_date_a > diff_date_b:
            best_course = course_search

    return best_course


def normalize_string(text: str) -> str:
    text = "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )

    text = re.sub(r"[\r\n]+", " ", text)
    text = re.sub(r"\s+", " ", text)

    text = text.replace("\\", "/")

    text = text.strip()

    text = text.lower()

    return text


def get_class_name(requirement):
    course_name = requirement.get("course", "")
    splits = course_name.split('-')
    if len(splits) > 0:
        course_name = (
            normalize_string(splits[0])
            .removeprefix("curso:")
            .strip()
            .replace(" ", "_")
        )
    return course_name

def build():
    OUTPUT.mkdir(exist_ok=True)

    courses = load_courses()

    departaments = list(dict.fromkeys([ course["departament"] for course in courses ]))

    for course in courses:
        departament = course["departament"]
        filename = course["file"].stem
        course_data = course["data"]

        output_dir = OUTPUT / departament
        output_dir.mkdir(parents=True, exist_ok=True)

        raw_date = str(course_data.get("updated_at", "19700101000000"))
        timestamp = datetime.strptime(raw_date, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)

        def search_child(course, requirement, dot, number = 65, last_number = 65, edge_type = ""):
            dot.node(chr(number), course["file"].stem)
            if number != last_number:
                dot.edge(chr(number), chr(last_number), label=edge_type)
            last_number = number

            class_name = get_class_name(requirement)
            requirements = requirement.get("requirements", [])

            for r in requirements:
                best_course = find_nearest_course(courses, course, r)
                if best_course is None:
                    number += 1
                    dot.node(chr(number), normalize_code(r.get("code")))
                    dot.edge(chr(last_number), chr(number))

                    continue
                for rr in best_course["data"].get("requirements", []):
                    if get_class_name(rr) == class_name:
                        number += 1
                        search_child(best_course, rr, dot, number, last_number, edge_type=r.get("type"))
                        break

        requirements = course_data.get("requirements", [])
        output_graphs = []
        for requirement in requirements:
            dot = graphviz.Digraph(comment='Requirements')
            dot.attr(rankdir='RL')
            search_child(course, requirement, dot)
            output_graph = output_dir / str(course["file"].stem + f'__{get_class_name(requirement)}')
            output_graphs.append(Path(departament) / course["file"].stem + f'__{get_class_name(requirement)}.svg')

            print(output_graph)
            dot.render(output_graph, format='svg')

        html = course_template.render(
            base_url=SITE_PREFIX,
            course=course["data"].get("courses", {}),
            departament=departament,
            departaments=departaments,
            timestamp=timestamp.strftime("%d/%m/%Y"),
            url=course["data"].get("url", ""),
            graphs=output_graphs
        )

        output_file = output_dir / f"{filename}.html"

        output_file.write_text(html, encoding="utf-8")

    index = index_template.render(
        base_url=SITE_PREFIX,
        departaments=departaments
    )
    (OUTPUT / "index.html").write_text(index, encoding="utf-8")

    for d in departaments:
        filtered_data = [course for course in courses if course["departament"] == d]

        departament = departament_template.render(
            base_url=SITE_PREFIX,
            departaments=departaments,
            departament=d,
            courses=filtered_data
        )
        (OUTPUT / f"{d}.html").write_text(departament, encoding="utf-8")

    config = ConfigParser()
    config.read(Path("generator") / "theme.conf")

    theme_conf = {
        f"theme_{key}": value
        for key, value in config["options"].items()
    }

    output_dir = OUTPUT / "assets"
    output_dir.mkdir(parents=True, exist_ok=True)
    css = css_template.render(base_url=SITE_PREFIX, **theme_conf)

    output_file = output_dir / "style.css"

    output_file.write_text(css, encoding="utf-8")


if __name__ == "__main__":
    build()
