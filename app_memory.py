import streamlit as st
from PIL import Image, ImageDraw, ImageFont
from textwrap import fill
import zipfile
import tempfile
import os
import json
from io import BytesIO


# ---------- Hulpfuncties ----------

def parse_pairs(text: str):
    """
    Verwacht regels in de vorm: woord1;woord2 of woord1,woord2
    Lege regels worden overgeslagen.
    """
    pairs = []
    for line in text.strip().split("\n"):
        line = line.strip()
        if not line:
            continue

        # scheidingsteken bepalen (; of ,)
        if ";" in line:
            sep = ";"
        elif "," in line:
            sep = ","
        else:
            st.warning(f"Overgeslagen (geen ';' of ',' gevonden): {line}")
            continue

        a, b = line.split(sep, 1)
        pairs.append((a.strip(), b.strip()))
    return pairs


def create_text_card(text, filename, img_dir,
                     img_width=300, img_height=180,
                     bg_color=(255, 255, 255),
                     text_color=(0, 0, 0)):
    """
    Maakt een PNG met tekst en slaat die op in img_dir/filename.
    Geeft het pad terug zoals dat in content.json moet komen.
    """
    img = Image.new("RGB", (img_width, img_height), bg_color)
    draw = ImageDraw.Draw(img)

    # lettertype proberen
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 80)
    except Exception:
        font = ImageFont.load_default()

    wrapped = fill(text, width=10) #15 vervangen door 10
    bbox = draw.multiline_textbbox((0, 0), wrapped, font=font, align="center")
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    x = (img_width - tw) / 2
    y = (img_height - th) / 2
    draw.multiline_text((x, y), wrapped, font=font,
                        fill=text_color, align="center")

    path = os.path.join(img_dir, filename)
    img.save(path)
    # In content.json worden paden relatief t.o.v. /content/ gebruikt
    return "images/" + filename


def build_h5p_from_template(template_bytes: bytes, word_pairs, output_filename="memory_from_text.h5p"):
    """
    Neemt een H5P-template (Image Pairing), genereert kaarten
    en geeft bytes van een nieuw H5P-bestand terug.
    """
    # tijdelijke dir voor uitpakken en werken
    with tempfile.TemporaryDirectory() as tmpdir:
        # we schrijven de meegegeven template_bytes weg als template.h5p
        template_path = os.path.join(tmpdir, "template.h5p")
        with open(template_path, "wb") as f:
            f.write(template_bytes)

        workdir = os.path.join(tmpdir, "h5p_work")
        os.makedirs(workdir, exist_ok=True)

        # Template uitpakken
        with zipfile.ZipFile(template_path, "r") as z:
            z.extractall(workdir)

        # Afbeeldingenmap
        img_dir = os.path.join(workdir, "content", "images")
        os.makedirs(img_dir, exist_ok=True)

        # Afbeeldingen genereren
        image_pairs_paths = []
        for i, (left, right) in enumerate(word_pairs, start=1):
            n = f"{i:02d}"
            fname_a = f"pair{n}_a_{left}.png"
            fname_b = f"pair{n}_b_{right}.png"

            path_a = create_text_card(left, fname_a, img_dir)
            path_b = create_text_card(right, fname_b, img_dir)

            desc = f"{left} ↔ {right}"
            image_pairs_paths.append((path_a, path_b, desc))

        # content.json aanpassen
        content_json_path = os.path.join(workdir, "content", "content.json")
        with open(content_json_path, "r", encoding="utf-8") as f:
            content = json.load(f)

        cards = []
        for (path_a, path_b, desc) in image_pairs_paths:
            card = {
                "image": {
                    "path": path_a,
                    "mime": "image/png",
                    "copyright": {
                        "license": "U"
                    }
                },
                "match": {
                    "path": path_b,
                    "mime": "image/png",
                    "copyright": {
                        "license": "U"
                    }
                },
                # optioneel, wordt gebruikt als feedbacktekst bij een goed paar
                "description": desc
            }
            cards.append(card)

        content["cards"] = cards

        with open(content_json_path, "w", encoding="utf-8") as f:
            json.dump(content, f, ensure_ascii=False, indent=2)

        # Alles opnieuw zippen naar H5P
        output_bytes = BytesIO()
        with zipfile.ZipFile(output_bytes, "w", zipfile.ZIP_DEFLATED) as z:
            for root, dirs, files in os.walk(workdir):
                for file in files:
                    fullpath = os.path.join(root, file)
                    relpath = os.path.relpath(fullpath, workdir)
                    z.write(fullpath, relpath)

        output_bytes.seek(0)
        return output_bytes, output_filename


# ---------- Streamlit UI ----------

# de template staat in de map templates en heet memory-template.h5p
TEMPLATE_PATH = os.path.join("templates", "memory-template.h5p")

# Logo bovenaan tonen (logo.png in dezelfde map als dit script)
#from pathlib import Path
#import streamlit as st

#LOGO_PATH = Path("logo.png")
#if LOGO_PATH.exists():
#    st.image(str(LOGO_PATH), width=400)  # pas breedte aan naar wens

logo_path = "logo.png"
if os.path.exists(logo_path):
    st.image(logo_path, width=400)
else:
    st.warning(f"Logo '{logo_path}' niet gevonden.")


st.title("H5P Memory / Image Pairing generator uit tekst")

st.markdown(
    "Deze tool gebruikt automatisch de standaardtemplate "
    "`templates/memory-template.h5p`.\n\n"
    "1. Zorg dat `templates/memory-template.h5p` bestaat.\n"
    "2. Vul woordparen in (`woord1;woord2` per regel).\n"
    "3. Klik op **Genereer H5P** en download het bestand."
)

# Optioneel: kleine check en info voor de gebruiker
if not os.path.exists(TEMPLATE_PATH):
    st.error("Template 'templates/memory-template.h5p' niet gevonden.")
else:
    st.info(f"Template gevonden: `{TEMPLATE_PATH}`")

default_text = "hond;dog\nkat;cat\nhuis;house"
text_input = st.text_area(
    "Woordparen",
    value=default_text,
    height=200,
    help="Gebruik ';' of ',' als scheidingsteken. Eén paar per regel."
)

if st.button("Genereer H5P"):
    # Controleer of template bestaat
    if not os.path.exists(TEMPLATE_PATH):
        st.error("Template 'templates/memory-template.h5p' niet gevonden. "
                 "Controleer het pad en de bestandsnaam.")
    else:
        pairs = parse_pairs(text_input)
        if not pairs:
            st.error("Geen geldige woordparen gevonden.")
        else:
            st.write(f"{len(pairs)} woordparen gevonden, H5P wordt opgebouwd…")

            # Template inladen
            with open(TEMPLATE_PATH, "rb") as f:
                template_bytes = f.read()

            output_bytes, out_name = build_h5p_from_template(
                template_bytes,
                pairs,
                output_filename="memory_from_text.h5p"
            )

            st.success("Klaar! Download je H5P-bestand hieronder.")
            st.download_button(
                "Download H5P",
                data=output_bytes,
                file_name=out_name,
                mime="application/zip"
            )
