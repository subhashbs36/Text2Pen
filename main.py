#Importing Library
# import argparse
import random
from PIL import Image, ImageDraw, ImageFont
import gradio as gr
import io
import os
import tempfile

A4_WIDTH, A4_HEIGHT = 2480, 3508  # A4 at 300dpi in pixels

DEMO_TEXT = """This is a demo of the Text2Pen!
- You can type or paste your own text here.
- Or upload a .txt file.
- Choose a handwriting font, font size, and more.
- Try different columns and jitters for a natural look.
Enjoy!"""

# Optionally, provide some bundled fonts/backgrounds
BUILTIN_FONTS = {
    "Julian Hand": "fonts/QEJulianDean.ttf",
    "Kevin Flower": "fonts/QEKevinKnowles.ttf",
    "Upload your own": None
}
BUILTIN_BGS = {
    "Blank (White)": None,
    "Ruled Paper": "backgrounds/ruled_a4.png",
    "Upload your own": None
}

def create_new_page(bg_path=None, bg_img=None):
    if bg_img is not None:
        bg = bg_img.convert("RGBA")
        if bg.size != (A4_WIDTH, A4_HEIGHT):
            bg = bg.resize((A4_WIDTH, A4_HEIGHT), Image.LANCZOS)
        return bg
    if bg_path:
        try:
            bg = Image.open(bg_path).convert("RGBA")
            if bg.size != (A4_WIDTH, A4_HEIGHT):
                bg = bg.resize((A4_WIDTH, A4_HEIGHT), Image.LANCZOS)
            return bg
        except Exception:
            pass
    # fallback: blank white A4
    return Image.new("RGBA", (A4_WIDTH, A4_HEIGHT), (255,255,255,255))

def get_text_size(text, font):
    if hasattr(font, "getbbox"):
        bbox = font.getbbox(text)
        width = bbox[2] - bbox[0]
        height = bbox[3] - bbox[1]
        return width, height
    else:
        return font.getsize(text)

# Ensure output folders exist
GENERATED_IMG_DIR = "generated/images"
GENERATED_PDF_DIR = "generated/pdfs"
os.makedirs(GENERATED_IMG_DIR, exist_ok=True)
os.makedirs(GENERATED_PDF_DIR, exist_ok=True)

def handwriting_render(
    textfile,
    textinput,
    font_choice,
    fontfile,
    fontsize,
    linespacing,
    margin,
    jitter,
    columns,
    bg_choice,
    bgfile,
    color,
    preview_first,
    download_pdf=False  # new argument to control PDF generation
):
    # Text: file takes priority, else textarea
    if textfile is not None:
        text = textfile.read().decode("utf-8")
    elif textinput and textinput.strip():
        text = textinput
    else:
        return None, None

    # Font: built-in or uploaded
    font_path = BUILTIN_FONTS.get(font_choice)
    if font_path is None and fontfile is not None:
        font_path = fontfile.name
    try:
        font = ImageFont.truetype(font_path, fontsize)
    except Exception:
        font = ImageFont.load_default()

    # BG: built-in or uploaded
    bg_path = BUILTIN_BGS.get(bg_choice)
    bg_img = None
    if bg_path is None and bgfile is not None:
        bg_img = Image.open(bgfile).convert("RGBA")
    elif bg_path is not None:
        try:
            bg_img = Image.open(bg_path).convert("RGBA")
        except Exception:
            bg_img = None

    col_count = int(columns)
    col_width = (A4_WIDTH - (col_count + 1) * margin) // col_count

    pages = []
    BG = create_new_page(bg_img=bg_img)
    draw = ImageDraw.Draw(BG)
    sheet_width, sheet_height = BG.size

    col = 0
    gap = margin
    ht = margin

    words = text.replace("\n", " \n ").split(" ")

    for word in words:
        if word == "\n":
            gap = margin + col * (col_width + margin)
            ht += fontsize + linespacing
            continue
        word_width, word_height = get_text_size(word, font)
        # Word wrapping in column
        if gap + word_width > margin + (col + 1) * col_width + col * margin:
            gap = margin + col * (col_width + margin)
            ht += fontsize + linespacing
        # If column overflows vertically, move to next column or page
        if ht + word_height > sheet_height - margin:
            if col < col_count - 1:
                col += 1
                gap = margin + col * (col_width + margin)
                ht = margin
            else:
                pages.append(BG)
                BG = create_new_page(bg_img=bg_img)
                draw = ImageDraw.Draw(BG)
                col = 0
                gap = margin
                ht = margin
        # Draw each character with jitter
        for ch in word:
            ch_width, ch_height = get_text_size(ch, font)
            jitter_x = random.randint(-jitter, jitter) if jitter > 0 else 0
            jitter_y = random.randint(-jitter, jitter) if jitter > 0 else 0
            draw.text((gap + jitter_x, ht + jitter_y), ch, font=font, fill=color)
            gap += ch_width
        gap += get_text_size(" ", font)[0]
    pages.append(BG)
    # Prepare outputs
    img_list = []
    if preview_first:
        pages_to_show = [pages[0]]
    else:
        pages_to_show = pages

    # Save images to disk and collect their filepaths for Gradio Gallery
    img_paths = []
    for idx, page in enumerate(pages_to_show):
        img_filename = os.path.join(GENERATED_IMG_DIR, f"handwriting_page_{idx+1}.png")
        page.save(img_filename)
        img_paths.append(img_filename)

    # Only generate PDF if requested
    pdf_filename = None
    if download_pdf:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_pdf:
            if len(pages) == 1:
                pages[0].save(tmp_pdf.name, format="PDF", resolution=300)
            else:
                pages[0].save(tmp_pdf.name, format="PDF", save_all=True, append_images=pages[1:], resolution=300)
            pdf_filename = tmp_pdf.name

    return img_paths, pdf_filename

def gradio_ui():
    with gr.Blocks(theme=gr.themes.Soft()) as demo:
        gr.Markdown(
            """
            # ✍️ Text2Pen
            Easily convert your text into realistic handwriting on A4 paper.
            """
        )
        with gr.Tab("Text & Output"):
            with gr.Row(equal_height=True):
                with gr.Column(scale=2):
                    textinput = gr.Textbox(
                        label="Enter Text",
                        value=DEMO_TEXT,
                        lines=12,
                        max_lines=30,
                        placeholder="Type or paste your text here..."
                    )
                    textfile = gr.File(label="Or Upload Text File (.txt)", file_types=[".txt"])
                    run_btn = gr.Button("Generate Handwriting", elem_id="generate-btn")
                with gr.Column(scale=1, min_width=180):
                    gallery = gr.Gallery(label="Preview Pages", columns=1, height=500)
                    pdfout = gr.File(label="Download PDF")
                    pdf_btn = gr.Button("Generate & Download PDF", elem_id="pdf-btn")

        with gr.Tab("Customization"):
            with gr.Row():
                with gr.Column(scale=1):
                    gr.Markdown("### Advanced Options")
                    fontsize = gr.Slider(24, 120, value=48, step=1, label="Font Size (pt)")
                    linespacing = gr.Slider(0, 50, value=10, step=1, label="Line Spacing (px)")
                    margin = gr.Slider(20, 200, value=70, step=1, label="Margin (px)")
                    jitter = gr.Slider(0, 10, value=0, step=1, label="Jitter (px, for natural look)")
                    columns = gr.Radio(choices=["1", "2", "3"], value="1", label="Columns per Page")
                    preview_first = gr.Checkbox(label="Preview Only First Page", value=True)
                with gr.Column(scale=1):
                    gr.Markdown("### Font Options")
                    font_choice = gr.Dropdown(list(BUILTIN_FONTS.keys()), value="Julian Hand", label="Handwriting Font")
                    fontfile = gr.File(label="Or Upload TTF Font", file_types=[".ttf"])
                    gr.Markdown("### Background Options")
                    color = gr.ColorPicker(label="Handwriting Color", value="#000000")
                    bg_choice = gr.Dropdown(list(BUILTIN_BGS.keys()), value="Blank (White)", label="Background")
                    bgfile = gr.File(label="Or Upload Background Image (A4 PNG/JPG)", file_types=[".png", ".jpg", ".jpeg"])

        # Link the customization tab values to the main tab
        run_btn.click(
            lambda *args: handwriting_render(*args, download_pdf=False),
            inputs=[
                textfile, textinput, font_choice, fontfile, fontsize, linespacing, margin,
                jitter, columns, bg_choice, bgfile, color, preview_first
            ],
            outputs=[gallery, pdfout]  # Always output both, but pdfout will be None unless requested
        )
        # Add a separate button for PDF download
        pdf_btn.click(
            lambda *args: handwriting_render(*args, download_pdf=True),
            inputs=[
                textfile, textinput, font_choice, fontfile, fontsize, linespacing, margin,
                jitter, columns, bg_choice, bgfile, color, preview_first
            ],
            outputs=[gallery, pdfout]
        )
    demo.launch()

if __name__ == "__main__":
    gradio_ui()

