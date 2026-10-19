import os
import math
import json
import shutil
from PIL import Image, ImageDraw, ImageFilter, ImageFont

def get_font(size=20, bold=False):
    try:
        font_name = "Helvetica" if not bold else "Helvetica-Bold"
        return ImageFont.truetype(font_name, size)
    except Exception:
        try:
            return ImageFont.truetype("Arial", size)
        except Exception:
            return ImageFont.load_default()

def apply_die_cut_and_shadow(img, outline_width=6, shadow_blur=8, shadow_alpha=0.28):
    """Adds a die-cut white vinyl border and subtle natural shadow to a transparent image."""
    w, h = img.size
    pad = outline_width + shadow_blur * 2 + 4
    canvas = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
    
    alpha = img.getchannel("A")
    # Expand alpha to create die-cut white outline
    expanded_alpha = alpha.filter(ImageFilter.MaxFilter(outline_width * 2 + 1))
    
    # White vinyl outline layer
    white_outline = Image.new("RGBA", (w, h), (255, 255, 255, 255))
    white_outline.putalpha(expanded_alpha)
    
    # Soft realistic drop shadow
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    sh_alpha = expanded_alpha.point(lambda v: int(v * shadow_alpha))
    shadow.paste(Image.new("RGBA", (w, h), (24, 18, 16, 255)), (pad + 2, pad + 5), sh_alpha)
    shadow = shadow.filter(ImageFilter.GaussianBlur(shadow_blur))
    
    # Composite: shadow -> white outline -> original artwork
    canvas = Image.alpha_composite(canvas, shadow)
    canvas.paste(white_outline, (pad, pad), white_outline)
    canvas.paste(img, (pad, pad), img)
    return canvas

def supersampled_canvas(w, h, scale=3):
    return Image.new("RGBA", (w * scale, h * scale), (0, 0, 0, 0)), scale

def downsample(canvas):
    w, h = canvas.size
    return canvas.resize((w // 3, h // 3), Image.Resampling.LANCZOS)

# ==============================================================================
# CITY LIFE ARTWORK
# ==============================================================================
def draw_city_taxi(w=380, h=240):
    im, s = supersampled_canvas(w, h)
    d = ImageDraw.Draw(im)
    
    # Yellow taxi cab body
    body_col = (252, 204, 34, 255)
    dark_yellow = (226, 175, 18, 255)
    d.rounded_rectangle([40*s, 90*s, 340*s, 195*s], radius=24*s, fill=body_col)
    
    # Cabin roof (sloped)
    cabin_pts = [(90*s, 90*s), (135*s, 38*s), (245*s, 38*s), (285*s, 90*s)]
    d.polygon(cabin_pts, fill=body_col)
    
    # Windshield and windows
    win_col = (195, 225, 240, 240)
    d.polygon([(98*s, 86*s), (138*s, 44*s), (180*s, 44*s), (180*s, 86*s)], fill=win_col)
    d.polygon([(190*s, 86*s), (190*s, 44*s), (240*s, 44*s), (275*s, 86*s)], fill=win_col)
    
    # Roof TAXI sign
    d.rounded_rectangle([165*s, 18*s, 215*s, 38*s], radius=6*s, fill=(255, 255, 255, 255), outline=(30, 30, 30, 255), width=2*s)
    font = get_font(13*s, bold=True)
    d.text((190*s, 28*s), "TAXI", font=font, fill=(20, 20, 20, 255), anchor="mm")
    
    # Checkerboard stripe across middle
    stripe_y = 128*s
    stripe_h = 16*s
    num_blocks = 18
    bw = (300*s) / num_blocks
    for i in range(num_blocks):
        bx = 40*s + i * bw
        col = (25, 25, 25, 255) if i % 2 == 0 else (255, 255, 255, 255)
        d.rectangle([bx, stripe_y, bx + bw, stripe_y + stripe_h], fill=col)
        
    # Bumpers
    d.rounded_rectangle([30*s, 165*s, 60*s, 190*s], radius=8*s, fill=(200, 205, 210, 255))
    d.rounded_rectangle([320*s, 165*s, 350*s, 190*s], radius=8*s, fill=(200, 205, 210, 255))
    
    # Headlights & Taillights
    d.ellipse([45*s, 120*s, 65*s, 140*s], fill=(255, 245, 180, 255), outline=(220, 180, 50, 255), width=2*s)
    d.ellipse([315*s, 120*s, 335*s, 140*s], fill=(235, 60, 50, 255))
    
    # Wheels
    wheel_col = (35, 35, 38, 255)
    hub_col = (210, 215, 220, 255)
    d.ellipse([75*s, 160*s, 135*s, 220*s], fill=wheel_col)
    d.ellipse([92*s, 177*s, 118*s, 203*s], fill=hub_col)
    
    d.ellipse([245*s, 160*s, 305*s, 220*s], fill=wheel_col)
    d.ellipse([262*s, 177*s, 288*s, 203*s], fill=hub_col)
    
    return apply_die_cut_and_shadow(downsample(im))

def draw_city_buildings(w=360, h=360):
    im, s = supersampled_canvas(w, h)
    d = ImageDraw.Draw(im)
    
    # Base skyscrapers silhouette with terracotta, slate blue, and charcoal
    d.rounded_rectangle([40*s, 130*s, 130*s, 330*s], radius=8*s, fill=(65, 80, 95, 255))
    d.rounded_rectangle([115*s, 60*s, 235*s, 330*s], radius=8*s, fill=(45, 52, 60, 255))
    d.polygon([(175*s, 20*s), (170*s, 60*s), (180*s, 60*s)], fill=(180, 190, 200, 255)) # Spire
    d.rounded_rectangle([220*s, 110*s, 320*s, 330*s], radius=8*s, fill=(195, 110, 85, 255))
    
    # Windows glowing
    win_col = (255, 238, 170, 220)
    for row in range(8):
        for col in range(3):
            wx = 135*s + col * 32*s
            wy = 85*s + row * 28*s
            if (row + col) % 3 != 0:
                d.rounded_rectangle([wx, wy, wx + 18*s, wy + 16*s], radius=2*s, fill=win_col)
                
    for row in range(6):
        for col in range(2):
            wx = 55*s + col * 32*s
            wy = 155*s + row * 26*s
            if (row * 2 + col) % 4 != 0:
                d.rounded_rectangle([wx, wy, wx + 16*s, wy + 14*s], radius=2*s, fill=(240, 245, 255, 200))
                
    for row in range(6):
        for col in range(2):
            wx = 245*s + col * 36*s
            wy = 135*s + row * 30*s
            if (row + col) % 2 == 0:
                d.rounded_rectangle([wx, wy, wx + 20*s, wy + 18*s], radius=2*s, fill=win_col)
                
    return apply_die_cut_and_shadow(downsample(im))

def draw_city_street_sign(w=360, h=260):
    im, s = supersampled_canvas(w, h)
    d = ImageDraw.Draw(im)
    
    # Dark metal signpost
    d.rectangle([168*s, 40*s, 192*s, 240*s], fill=(70, 75, 80, 255))
    d.ellipse([162*s, 25*s, 198*s, 50*s], fill=(210, 180, 70, 255)) # Brass finial
    
    # Broadway Green sign (angled slightly)
    sign_green = (24, 98, 56, 255)
    d.rounded_rectangle([30*s, 55*s, 270*s, 115*s], radius=12*s, fill=sign_green, outline=(255, 255, 255, 255), width=3*s)
    font_bold = get_font(24*s, bold=True)
    font_sm = get_font(14*s, bold=True)
    d.text((140*s, 85*s), "BROADWAY", font=font_bold, fill=(255, 255, 255, 255), anchor="mm")
    
    # 5th AVE sign
    d.rounded_rectangle([110*s, 125*s, 330*s, 185*s], radius=12*s, fill=sign_green, outline=(255, 255, 255, 255), width=3*s)
    d.text((220*s, 155*s), "5TH AVE", font=font_bold, fill=(255, 255, 255, 255), anchor="mm")
    
    return apply_die_cut_and_shadow(downsample(im))

def draw_city_subway_map(w=340, h=340):
    im, s = supersampled_canvas(w, h)
    d = ImageDraw.Draw(im)
    
    # Folded cream parchment map
    d.rounded_rectangle([30*s, 30*s, 310*s, 310*s], radius=14*s, fill=(250, 246, 238, 255), outline=(215, 205, 190, 255), width=2*s)
    # Subtle fold lines
    d.line([(170*s, 30*s), (170*s, 310*s)], fill=(230, 220, 205, 255), width=2*s)
    d.line([(30*s, 170*s), (310*s, 170*s)], fill=(230, 220, 205, 255), width=2*s)
    
    # Metro Line 1 (Red)
    d.line([(50*s, 270*s), (140*s, 200*s), (200*s, 140*s), (290*s, 120*s)], fill=(238, 53, 36, 255), width=8*s)
    # Metro Line 2 (Blue)
    d.line([(60*s, 80*s), (140*s, 120*s), (200*s, 210*s), (270*s, 280*s)], fill=(0, 120, 210, 255), width=8*s)
    # Metro Line 3 (Yellow/Orange)
    d.line([(100*s, 50*s), (170*s, 170*s), (250*s, 220*s)], fill=(255, 160, 0, 255), width=8*s)
    
    # Stations (white dots with black outline)
    stations = [(140, 200), (200, 140), (140, 120), (200, 210), (170, 170), (100, 50), (290, 120)]
    for sx, sy in stations:
        d.ellipse([(sx-7)*s, (sy-7)*s, (sx+7)*s, (sy+7)*s], fill=(255, 255, 255, 255), outline=(30, 30, 30, 255), width=3*s)
        
    # Metro header
    font = get_font(15*s, bold=True)
    d.text((50*s, 52*s), "METRO MAP", font=font, fill=(50, 50, 50, 255), anchor="lt")
    return apply_die_cut_and_shadow(downsample(im))

def draw_city_traffic_light(w=200, h=380):
    im, s = supersampled_canvas(w, h)
    d = ImageDraw.Draw(im)
    
    # Black housing with rounded pill
    d.rounded_rectangle([40*s, 25*s, 160*s, 355*s], radius=28*s, fill=(35, 38, 42, 255), outline=(20, 22, 25, 255), width=3*s)
    
    # Visors over lights
    for y_center in [85, 190, 295]:
        d.arc([55*s, (y_center - 48)*s, 145*s, (y_center + 10)*s], 180, 360, fill=(25, 28, 30, 255), width=6*s)
        
    # Red light glowing
    d.ellipse([60*s, 45*s, 140*s, 125*s], fill=(245, 55, 45, 255), outline=(180, 20, 15, 255), width=3*s)
    d.ellipse([75*s, 58*s, 100*s, 80*s], fill=(255, 140, 130, 220)) # Specular highlight
    
    # Amber light
    d.ellipse([60*s, 150*s, 140*s, 230*s], fill=(255, 185, 30, 255), outline=(200, 130, 10, 255), width=3*s)
    d.ellipse([75*s, 163*s, 100*s, 185*s], fill=(255, 220, 120, 220))
    
    # Green light
    d.ellipse([60*s, 255*s, 140*s, 335*s], fill=(40, 210, 110, 255), outline=(20, 150, 70, 255), width=3*s)
    d.ellipse([75*s, 268*s, 100*s, 290*s], fill=(140, 255, 180, 220))
    
    return apply_die_cut_and_shadow(downsample(im))

def draw_city_transit_ticket(w=360, h=180):
    im, s = supersampled_canvas(w, h)
    d = ImageDraw.Draw(im)
    
    # Cream / Kraft vintage ticket
    d.rounded_rectangle([25*s, 25*s, 335*s, 155*s], radius=10*s, fill=(252, 244, 228, 255), outline=(220, 200, 175, 255), width=2*s)
    # Perforated stub cutouts on left and right
    d.ellipse([15*s, 80*s, 35*s, 100*s], fill=(0, 0, 0, 0))
    d.ellipse([325*s, 80*s, 345*s, 100*s], fill=(0, 0, 0, 0))
    
    # Red vintage stamp border inside
    d.rectangle([45*s, 38*s, 315*s, 142*s], outline=(205, 65, 55, 180), width=2*s)
    
    font_lg = get_font(26*s, bold=True)
    font_md = get_font(13*s, bold=True)
    font_mono = get_font(11*s, bold=False)
    
    d.text((180*s, 64*s), "CITY TRANSIT", font=font_lg, fill=(45, 45, 45, 255), anchor="mm")
    d.text((180*s, 95*s), "★ ONE WAY PASS • NO. 84920 ★", font=font_md, fill=(205, 65, 55, 255), anchor="mm")
    d.text((180*s, 122*s), "VALID ALL DAY • SUBWAY & TRAM", font=font_mono, fill=(90, 85, 80, 255), anchor="mm")
    
    return apply_die_cut_and_shadow(downsample(im))

# ==============================================================================
# TRAVEL ARTWORK
# ==============================================================================
def draw_travel_camera(w=360, h=280):
    im, s = supersampled_canvas(w, h)
    d = ImageDraw.Draw(im)
    
    # Camera lower body (black textured leatherette)
    d.rounded_rectangle([35*s, 95*s, 325*s, 245*s], radius=16*s, fill=(35, 36, 40, 255))
    # Camera top plate (brushed silver metal)
    d.rounded_rectangle([35*s, 65*s, 325*s, 105*s], radius=10*s, fill=(215, 220, 226, 255))
    
    # Shutter button & dials
    d.rounded_rectangle([60*s, 48*s, 95*s, 68*s], radius=4*s, fill=(185, 190, 198, 255))
    d.rounded_rectangle([250*s, 50*s, 290*s, 68*s], radius=4*s, fill=(185, 190, 198, 255))
    d.rounded_rectangle([105*s, 52*s, 140*s, 68*s], radius=4*s, fill=(230, 60, 50, 255)) # Red shutter accent
    
    # Flash / Viewfinder
    d.rounded_rectangle([255*s, 80*s, 295*s, 102*s], radius=4*s, fill=(235, 245, 255, 255), outline=(130, 140, 150, 255), width=2*s)
    
    # Big center lens (silver outer ring, black inner rings, blue optical reflection)
    cx, cy = 180*s, 160*s
    d.ellipse([(cx-68*s), (cy-68*s), (cx+68*s), (cy+68*s)], fill=(195, 200, 208, 255), outline=(150, 155, 165, 255), width=4*s)
    d.ellipse([(cx-56*s), (cy-56*s), (cx+56*s), (cy+56*s)], fill=(28, 30, 35, 255))
    d.ellipse([(cx-42*s), (cy-42*s), (cx+42*s), (cy+42*s)], fill=(20, 35, 60, 255))
    # Glare reflections
    d.ellipse([(cx-26*s), (cy-30*s), (cx-6*s), (cy-10*s)], fill=(140, 210, 255, 220))
    d.ellipse([(cx+14*s), (cy+10*s), (cx+26*s), (cy+22*s)], fill=(255, 255, 255, 180))
    
    return apply_die_cut_and_shadow(downsample(im))

def draw_travel_postcard(w=360, h=250):
    im, s = supersampled_canvas(w, h)
    d = ImageDraw.Draw(im)
    
    # Vintage ivory postcard
    d.rounded_rectangle([25*s, 25*s, 335*s, 225*s], radius=10*s, fill=(252, 248, 240, 255), outline=(225, 215, 200, 255), width=2*s)
    
    # Striped airmail border (red & blue chevrons)
    colors = [(225, 55, 50, 255), (45, 95, 185, 255)]
    stripe_w = 16*s
    # Top border
    for i in range(18):
        c = colors[i % 2]
        bx = 30*s + i * stripe_w
        d.polygon([(bx, 27*s), (bx + 12*s, 27*s), (bx + 6*s, 37*s), (bx - 6*s, 37*s)], fill=c)
    # Bottom border
    for i in range(18):
        c = colors[i % 2]
        bx = 30*s + i * stripe_w
        d.polygon([(bx, 215*s), (bx + 12*s, 215*s), (bx + 6*s, 223*s), (bx - 6*s, 223*s)], fill=c)
        
    # Dividing vertical line
    d.line([(180*s, 50*s), (180*s, 200*s)], fill=(210, 200, 185, 255), width=2*s)
    
    # Postage stamp on top right
    d.rectangle([260*s, 50*s, 315*s, 110*s], fill=(245, 235, 215, 255), outline=(180, 160, 140, 255), width=2*s)
    d.ellipse([275*s, 65*s, 300*s, 90*s], fill=(225, 75, 65, 255))
    
    # Postmark wavy stamp over stamp
    d.arc([240*s, 70*s, 280*s, 110*s], 0, 360, fill=(70, 70, 75, 220), width=2*s)
    d.line([(280*s, 80*s), (325*s, 80*s)], fill=(70, 70, 75, 220), width=2*s)
    d.line([(280*s, 92*s), (325*s, 92*s)], fill=(70, 70, 75, 220), width=2*s)
    
    # Handwritten message lines
    font = get_font(18*s, bold=False)
    d.text((50*s, 65*s), "Wish you were here! ✨", font=font, fill=(75, 70, 80, 255))
    for y in [105, 135, 165]:
        d.line([(45*s, y*s), (165*s, y*s)], fill=(215, 205, 195, 255), width=2*s)
        
    return apply_die_cut_and_shadow(downsample(im))

def draw_travel_suitcase(w=360, h=300):
    im, s = supersampled_canvas(w, h)
    d = ImageDraw.Draw(im)
    
    # Cognac leather trunk body
    body_col = (195, 120, 65, 255)
    d.rounded_rectangle([45*s, 85*s, 315*s, 265*s], radius=22*s, fill=body_col, outline=(150, 85, 40, 255), width=3*s)
    
    # Brass reinforced corners
    corner_col = (235, 190, 80, 255)
    corners = [(45, 85), (295, 85), (45, 245), (295, 245)]
    for cx, cy in corners:
        d.rounded_rectangle([cx*s, cy*s, (cx+20)*s, (cy+20)*s], radius=6*s, fill=corner_col)
        
    # Vertical leather straps
    strap_col = (115, 65, 30, 255)
    d.rectangle([105*s, 85*s, 130*s, 265*s], fill=strap_col)
    d.rectangle([230*s, 85*s, 255*s, 265*s], fill=strap_col)
    # Brass buckles
    d.rounded_rectangle([102*s, 165*s, 133*s, 185*s], radius=4*s, fill=corner_col)
    d.rounded_rectangle([227*s, 165*s, 258*s, 185*s], radius=4*s, fill=corner_col)
    
    # Suitcase handle on top
    d.arc([145*s, 35*s, 215*s, 105*s], 180, 360, fill=strap_col, width=12*s)
    
    # Travel sticker on suitcase
    d.ellipse([145*s, 115*s, 215*s, 185*s], fill=(245, 240, 220, 255), outline=(210, 50, 45, 255), width=3*s)
    font = get_font(14*s, bold=True)
    d.text((180*s, 150*s), "PARIS", font=font, fill=(210, 50, 45, 255), anchor="mm")
    
    return apply_die_cut_and_shadow(downsample(im))

def draw_travel_passport_stamp(w=300, h=300):
    im, s = supersampled_canvas(w, h)
    d = ImageDraw.Draw(im)
    
    # Blue / Violet vintage rubber ink stamp
    stamp_col = (40, 75, 165, 230)
    d.ellipse([35*s, 35*s, 265*s, 265*s], outline=stamp_col, width=6*s)
    d.ellipse([50*s, 50*s, 250*s, 250*s], outline=stamp_col, width=2*s)
    
    font_lg = get_font(24*s, bold=True)
    font_md = get_font(18*s, bold=True)
    font_sm = get_font(14*s, bold=True)
    
    d.text((150*s, 85*s), "PASSPORT CONTROL", font=font_sm, fill=stamp_col, anchor="mm")
    d.text((150*s, 125*s), "★ ADMITTED ★", font=font_lg, fill=stamp_col, anchor="mm")
    d.text((150*s, 165*s), "19 OCT 2024", font=font_md, fill=stamp_col, anchor="mm")
    d.text((150*s, 205*s), "INTERNATIONAL AIRPORT", font=font_sm, fill=stamp_col, anchor="mm")
    
    return apply_die_cut_and_shadow(downsample(im), outline_width=5)

def draw_travel_location_pin(w=200, h=280):
    im, s = supersampled_canvas(w, h)
    d = ImageDraw.Draw(im)
    
    # Red enamel map pin
    cx, cy = 100*s, 95*s
    r = 65*s
    # Tear-drop bottom point
    d.polygon([(cx - 50*s, cy + 30*s), (cx + 50*s, cy + 30*s), (cx, 245*s)], fill=(225, 45, 40, 255))
    d.ellipse([(cx - r), (cy - r), (cx + r), (cy + r)], fill=(235, 55, 45, 255))
    
    # White center circle
    d.ellipse([(cx - 28*s), (cy - 28*s), (cx + 28*s), (cy + 28*s)], fill=(255, 255, 255, 255))
    # Specular highlight
    d.arc([(cx - 50*s), (cy - 50*s), (cx + 10*s), (cy + 10*s)], 190, 270, fill=(255, 180, 180, 220), width=6*s)
    
    return apply_die_cut_and_shadow(downsample(im))

# ==============================================================================
# CAFE AND FOOD ARTWORK
# ==============================================================================
def draw_cafe_latte(w=320, h=320):
    im, s = supersampled_canvas(w, h)
    d = ImageDraw.Draw(im)
    
    cx, cy = 160*s, 160*s
    # Terracotta saucer
    d.ellipse([(cx-135*s), (cy-135*s), (cx+135*s), (cy+135*s)], fill=(220, 155, 130, 255), outline=(180, 110, 90, 255), width=3*s)
    # Cup rim
    d.ellipse([(cx-105*s), (cy-105*s), (cx+105*s), (cy+105*s)], fill=(252, 248, 242, 255), outline=(225, 215, 200, 255), width=4*s)
    # Rich coffee crema
    d.ellipse([(cx-92*s), (cy-92*s), (cx+92*s), (cy+92*s)], fill=(160, 100, 60, 255))
    # Steamed milk heart latte art
    milk_col = (252, 246, 238, 255)
    # Heart top lobes
    d.ellipse([(cx-45*s), (cy-45*s), cx, (cy+5*s)], fill=milk_col)
    d.ellipse([cx, (cy-45*s), (cx+45*s), (cy+5*s)], fill=milk_col)
    # Heart point
    d.polygon([(cx-42*s), (cy-10*s), (cx+42*s), (cy-10*s), cx, (cy+50*s)], fill=milk_col)
    
    return apply_die_cut_and_shadow(downsample(im))

def draw_cafe_croissant(w=360, h=260):
    im, s = supersampled_canvas(w, h)
    d = ImageDraw.Draw(im)
    
    # Golden flaky buttery croissant crescent
    cx, cy = 180*s, 140*s
    golden = (235, 170, 70, 255)
    toasted = (195, 115, 35, 255)
    
    # Main curved body
    d.chord([40*s, 60*s, 320*s, 240*s], 180, 360, fill=golden, outline=toasted, width=3*s)
    # Crescent tips curving in
    d.ellipse([40*s, 130*s, 120*s, 195*s], fill=golden, outline=toasted, width=2*s)
    d.ellipse([240*s, 130*s, 320*s, 195*s], fill=golden, outline=toasted, width=2*s)
    # Middle rolls & layers
    d.arc([80*s, 80*s, 180*s, 190*s], 150, 330, fill=toasted, width=4*s)
    d.arc([130*s, 70*s, 230*s, 190*s], 160, 340, fill=toasted, width=5*s)
    d.arc([180*s, 80*s, 280*s, 190*s], 160, 340, fill=toasted, width=4*s)
    
    return apply_die_cut_and_shadow(downsample(im))

def draw_cafe_cherries(w=300, h=300):
    im, s = supersampled_canvas(w, h)
    d = ImageDraw.Draw(im)
    
    # Curved green stems
    stem_col = (85, 145, 55, 255)
    d.arc([110*s, 40*s, 230*s, 220*s], 160, 270, fill=stem_col, width=6*s)
    d.arc([70*s, 40*s, 230*s, 240*s], 180, 280, fill=stem_col, width=6*s)
    # Leaf at stem junction
    d.polygon([(170*s, 50*s), (230*s, 35*s), (210*s, 65*s)], fill=(105, 175, 70, 255))
    
    # Left cherry
    cherry_col = (195, 20, 45, 255)
    dark_cherry = (140, 10, 30, 255)
    d.ellipse([70*s, 160*s, 160*s, 250*s], fill=cherry_col, outline=dark_cherry, width=3*s)
    d.ellipse([88*s, 175*s, 115*s, 195*s], fill=(255, 140, 160, 220)) # Gloss highlight
    
    # Right cherry
    d.ellipse([155*s, 175*s, 245*s, 265*s], fill=cherry_col, outline=dark_cherry, width=3*s)
    d.ellipse([173*s, 190*s, 200*s, 210*s], fill=(255, 140, 160, 220))
    
    return apply_die_cut_and_shadow(downsample(im))

def draw_cafe_matcha(w=240, h=360):
    im, s = supersampled_canvas(w, h)
    d = ImageDraw.Draw(im)
    
    # Tall glass tumbler
    d.rounded_rectangle([55*s, 60*s, 185*s, 315*s], radius=16*s, fill=(235, 245, 240, 120), outline=(190, 215, 200, 255), width=3*s)
    
    # White milk lower layer
    d.rounded_rectangle([60*s, 180*s, 180*s, 310*s], radius=12*s, fill=(252, 250, 245, 255))
    # Green matcha top layer
    matcha_col = (115, 165, 80, 255)
    d.rounded_rectangle([60*s, 75*s, 180*s, 210*s], radius=10*s, fill=matcha_col)
    
    # Ice cubes floating
    for ix, iy in [(75, 95), (120, 125), (85, 160)]:
        d.rounded_rectangle([ix*s, iy*s, (ix+35)*s, (iy+35)*s], radius=6*s, fill=(255, 255, 255, 180), outline=(210, 235, 220, 200), width=2*s)
        
    # Glass straw
    d.line([(145*s, 25*s), (105*s, 280*s)], fill=(255, 180, 120, 240), width=6*s)
    
    return apply_die_cut_and_shadow(downsample(im))

# ==============================================================================
# GIRLY AND COQUETTE ARTWORK
# ==============================================================================
def draw_coquette_bow(w=360, h=300):
    im, s = supersampled_canvas(w, h)
    d = ImageDraw.Draw(im)
    
    kx, ky = 180*s, 140*s
    pink_main = (255, 185, 200, 255)
    pink_shade = (235, 145, 165, 255)
    pink_border = (220, 125, 145, 255)
    
    # Left loop
    d.polygon([(kx, ky), (kx - 125*s, ky - 75*s), (kx - 145*s, ky), (kx - 110*s, ky + 55*s), (kx, ky)], fill=pink_main, outline=pink_border, width=2*s)
    # Right loop
    d.polygon([(kx, ky), (kx + 125*s, ky - 75*s), (kx + 145*s, ky), (kx + 110*s, ky + 55*s), (kx, ky)], fill=pink_main, outline=pink_border, width=2*s)
    
    # Left flowing ribbon tail
    d.polygon([(kx - 20*s, ky + 10*s), (kx - 95*s, ky + 135*s), (kx - 65*s, ky + 145*s), (kx - 10*s, ky + 30*s)], fill=pink_shade, outline=pink_border, width=2*s)
    # Right flowing ribbon tail
    d.polygon([(kx + 20*s, ky + 10*s), (kx + 95*s, ky + 135*s), (kx + 65*s, ky + 145*s), (kx + 10*s, ky + 30*s)], fill=pink_shade, outline=pink_border, width=2*s)
    
    # Center knot with pearl luster
    d.ellipse([(kx - 26*s), (ky - 26*s), (kx + 26*s), (ky + 26*s)], fill=(255, 205, 215, 255), outline=pink_border, width=2*s)
    
    return apply_die_cut_and_shadow(downsample(im))

def draw_coquette_gingham_tape(w=380, h=160):
    im, s = supersampled_canvas(w, h)
    d = ImageDraw.Draw(im)
    
    # Gingham tape strip with torn deckled ends
    tape_w, tape_h = 320*s, 80*s
    tx, ty = 30*s, 40*s
    
    # Base pink
    d.rectangle([tx, ty, tx + tape_w, ty + tape_h], fill=(255, 235, 240, 240))
    
    # Gingham checkered blocks
    block = 16*s
    for r in range(int(tape_h / block) + 1):
        for c in range(int(tape_w / block) + 1):
            bx = tx + c * block
            by = ty + r * block
            if (r + c) % 2 == 0:
                d.rectangle([bx, by, min(bx + block, tx + tape_w), min(by + block, ty + tape_h)], fill=(255, 175, 195, 190))
            elif r % 2 == 0:
                d.rectangle([bx, by, min(bx + block, tx + tape_w), min(by + block, ty + tape_h)], fill=(255, 205, 220, 150))
                
    # Jagged torn ends
    for i in range(10):
        jy = ty + i * 8*s
        d.polygon([(tx, jy), (tx - 6*s, jy + 4*s), (tx, jy + 8*s)], fill=(255, 255, 255, 0))
        d.polygon([(tx + tape_w, jy), (tx + tape_w + 6*s, jy + 4*s), (tx + tape_w, jy + 8*s)], fill=(255, 255, 255, 0))
        
    return apply_die_cut_and_shadow(downsample(im), outline_width=4)

def draw_coquette_heart_locket(w=280, h=280):
    im, s = supersampled_canvas(w, h)
    d = ImageDraw.Draw(im)
    
    cx, cy = 140*s, 140*s
    gold = (235, 185, 75, 255)
    gold_dark = (195, 140, 45, 255)
    
    # Top bail ring
    d.ellipse([(cx - 18*s), 30*s, (cx + 18*s), 65*s], outline=gold_dark, width=5*s)
    
    # Heart locket body
    d.ellipse([(cx - 75*s), (cy - 65*s), (cx + 5*s), (cy + 15*s)], fill=gold, outline=gold_dark, width=3*s)
    d.ellipse([(cx - 5*s), (cy - 65*s), (cx + 75*s), (cy + 15*s)], fill=gold, outline=gold_dark, width=3*s)
    d.polygon([(cx - 70*s), (cy - 5*s), (cx + 70*s), (cy - 5*s), cx, (cy + 95*s)], fill=gold, outline=gold_dark, width=3*s)
    
    # Keyhole in center
    d.ellipse([(cx - 10*s), (cy - 10*s), (cx + 10*s), (cy + 10*s)], fill=(60, 40, 20, 255))
    d.polygon([(cx - 7*s), cy, (cx + 7*s), cy, (cx + 12*s), (cy + 25*s), (cx - 12*s), (cy + 25*s)], fill=(60, 40, 20, 255))
    
    return apply_die_cut_and_shadow(downsample(im))

def draw_coquette_sparkle_heart(w=280, h=280):
    im, s = supersampled_canvas(w, h)
    d = ImageDraw.Draw(im)
    
    cx, cy = 140*s, 140*s
    pink = (255, 140, 175, 255)
    
    # Heart shape
    d.ellipse([(cx - 65*s), (cy - 55*s), (cx + 5*s), (cy + 15*s)], fill=pink)
    d.ellipse([(cx - 5*s), (cy - 55*s), (cx + 65*s), (cy + 15*s)], fill=pink)
    d.polygon([(cx - 60*s), (cy - 5*s), (cx + 60*s), (cy - 5*s), cx, (cy + 85*s)], fill=pink)
    
    # Sparkles (4-point stars)
    def draw_sparkle(x, y, r):
        d.polygon([(x, y - r), (x + r*0.3, y - r*0.3), (x + r, y), (x + r*0.3, y + r*0.3), (x, y + r), (x - r*0.3, y + r*0.3), (x - r, y), (x - r*0.3, y - r*0.3)], fill=(255, 235, 120, 255))
        
    draw_sparkle(55*s, 65*s, 22*s)
    draw_sparkle(225*s, 60*s, 26*s)
    draw_sparkle(215*s, 215*s, 18*s)
    
    return apply_die_cut_and_shadow(downsample(im))

# ==============================================================================
# NATURE ARTWORK
# ==============================================================================
def draw_nature_butterfly(w=360, h=300):
    im, s = supersampled_canvas(w, h)
    d = ImageDraw.Draw(im)
    
    cx, cy = 180*s, 150*s
    orange = (245, 120, 30, 255)
    black = (25, 25, 30, 255)
    
    # Upper left wing
    d.polygon([(cx, cy - 20*s), (cx - 130*s, cy - 90*s), (cx - 145*s, cy - 20*s), (cx - 90*s, cy + 30*s), (cx, cy)], fill=orange, outline=black, width=4*s)
    # Upper right wing
    d.polygon([(cx, cy - 20*s), (cx + 130*s, cy - 90*s), (cx + 145*s, cy - 20*s), (cx + 90*s, cy + 30*s), (cx, cy)], fill=orange, outline=black, width=4*s)
    
    # Lower left wing
    d.polygon([(cx, cy), (cx - 105*s, cy + 35*s), (cx - 95*s, cy + 115*s), (cx - 20*s, cy + 85*s), (cx, cy)], fill=orange, outline=black, width=4*s)
    # Lower right wing
    d.polygon([(cx, cy), (cx + 105*s, cy + 35*s), (cx + 95*s, cy + 115*s), (cx + 20*s, cy + 85*s), (cx, cy)], fill=orange, outline=black, width=4*s)
    
    # Monarch black vein lines
    d.line([(cx - 70*s, cy - 10*s), (cx - 130*s, cy - 50*s)], fill=black, width=3*s)
    d.line([(cx + 70*s, cy - 10*s), (cx + 130*s, cy - 50*s)], fill=black, width=3*s)
    
    # White dots on wing tips
    for dx in [-130, -120, -110, 110, 120, 130]:
        d.ellipse([(cx + dx*s - 3*s), (cy - 60*s), (cx + dx*s + 3*s), (cy - 54*s)], fill=(255, 255, 255, 255))
        
    # Center thorax & head
    d.rounded_rectangle([(cx - 10*s), (cy - 50*s), (cx + 10*s), (cy + 65*s)], radius=10*s, fill=black)
    # Antennae
    d.arc([(cx - 30*s), (cy - 90*s), (cx - 5*s), (cy - 45*s)], 180, 300, fill=black, width=3*s)
    d.arc([(cx + 5*s), (cy - 90*s), (cx + 30*s), (cy - 45*s)], 240, 360, fill=black, width=3*s)
    
    return apply_die_cut_and_shadow(downsample(im))

def draw_nature_daisy(w=300, h=300):
    im, s = supersampled_canvas(w, h)
    d = ImageDraw.Draw(im)
    
    cx, cy = 150*s, 150*s
    num_petals = 12
    # White petals radiating
    for i in range(num_petals):
        ang = (i / num_petals) * 2 * math.pi
        px = cx + math.cos(ang) * 65*s
        py = cy + math.sin(ang) * 65*s
        d.ellipse([(px - 22*s), (py - 22*s), (px + 22*s), (py + 22*s)], fill=(255, 255, 255, 255), outline=(230, 225, 215, 255), width=2*s)
        
    # Sunny golden center disc
    d.ellipse([(cx - 38*s), (cy - 38*s), (cx + 38*s), (cy + 38*s)], fill=(255, 195, 30, 255), outline=(215, 145, 15, 255), width=3*s)
    
    return apply_die_cut_and_shadow(downsample(im))

def draw_nature_ginkgo(w=300, h=300):
    im, s = supersampled_canvas(w, h)
    d = ImageDraw.Draw(im)
    
    cx, cy = 150*s, 130*s
    gold = (235, 180, 50, 255)
    stem_col = (180, 130, 40, 255)
    
    # Fan shape
    d.pieslice([(cx - 100*s), (cy - 100*s), (cx + 100*s), (cy + 100*s)], 210, 330, fill=gold, outline=stem_col, width=3*s)
    # Notch in middle of fan
    d.polygon([(cx - 15*s), (cy - 100*s), (cx + 15*s), (cy - 100*s), cx, (cy - 50*s)], fill=(0, 0, 0, 0))
    # Delicate veins radiating
    for deg in range(220, 325, 15):
        rad = math.radians(deg)
        d.line([cx, cy, cx + math.cos(rad) * 90*s, cy + math.sin(rad) * 90*s], fill=(215, 160, 35, 220), width=2*s)
    # Slender curved stem
    d.arc([(cx - 40*s), cy, (cx + 20*s), (cy + 130*s)], 0, 90, fill=stem_col, width=5*s)
    
    return apply_die_cut_and_shadow(downsample(im))

# ==============================================================================
# FASHION ARTWORK
# ==============================================================================
def draw_fashion_handbag(w=320, h=300):
    im, s = supersampled_canvas(w, h)
    d = ImageDraw.Draw(im)
    
    # Quilted black leather handbag
    d.rounded_rectangle([50*s, 100*s, 270*s, 255*s], radius=16*s, fill=(30, 32, 35, 255))
    
    # Quilted diamond pattern lines
    gold = (230, 190, 80, 255)
    for i in range(-3, 6):
        d.line([(50*s + i*40*s, 100*s), (50*s + (i+4)*40*s, 255*s)], fill=(55, 58, 65, 255), width=2*s)
        d.line([(270*s - i*40*s, 100*s), (270*s - (i+4)*40*s, 255*s)], fill=(55, 58, 65, 255), width=2*s)
        
    # Flap closure
    d.polygon([(50*s, 100*s), (270*s, 100*s), (250*s, 175*s), (70*s, 175*s)], fill=(22, 24, 26, 255), outline=(55, 58, 65, 255), width=2*s)
    # Gold turn-lock clasp
    d.rounded_rectangle([145*s, 160*s, 175*s, 185*s], radius=5*s, fill=gold)
    
    # Gold chain handle on top
    d.arc([90*s, 35*s, 230*s, 135*s], 180, 360, fill=gold, width=8*s)
    
    return apply_die_cut_and_shadow(downsample(im))

def draw_fashion_sunglasses(w=360, h=180):
    im, s = supersampled_canvas(w, h)
    d = ImageDraw.Draw(im)
    
    tortoise = (110, 55, 25, 255)
    lens_col = (35, 40, 48, 240)
    
    # Left oval rim
    d.ellipse([30*s, 40*s, 165*s, 135*s], fill=tortoise)
    d.ellipse([45*s, 52*s, 150*s, 122*s], fill=lens_col)
    
    # Right oval rim
    d.ellipse([195*s, 40*s, 330*s, 135*s], fill=tortoise)
    d.ellipse([210*s, 52*s, 315*s, 122*s], fill=lens_col)
    
    # Bridge between lenses
    d.arc([155*s, 60*s, 205*s, 95*s], 180, 360, fill=tortoise, width=8*s)
    # Temples / side arms
    d.line([(30*s, 65*s), (10*s, 50*s)], fill=tortoise, width=6*s)
    d.line([(330*s, 65*s), (350*s, 50*s)], fill=tortoise, width=6*s)
    
    # Glare lines on lenses
    d.line([(70*s, 60*s), (55*s, 110*s)], fill=(255, 255, 255, 140), width=4*s)
    d.line([(235*s, 60*s), (220*s, 110*s)], fill=(255, 255, 255, 140), width=4*s)
    
    return apply_die_cut_and_shadow(downsample(im))

def draw_fashion_lipstick(w=180, h=340):
    im, s = supersampled_canvas(w, h)
    d = ImageDraw.Draw(im)
    
    gold = (235, 185, 75, 255)
    gold_dark = (195, 140, 45, 255)
    red = (210, 25, 45, 255)
    
    # Black base tube
    d.rounded_rectangle([45*s, 175*s, 135*s, 310*s], radius=10*s, fill=(28, 30, 32, 255))
    # Gold middle collar
    d.rectangle([50*s, 115*s, 130*s, 175*s], fill=gold, outline=gold_dark, width=2*s)
    
    # Angled red lipstick bullet
    d.polygon([(58*s, 115*s), (122*s, 115*s), (122*s, 60*s), (58*s, 25*s)], fill=red)
    # Specular shine
    d.line([(68*s, 110*s), (68*s, 40*s)], fill=(255, 140, 160, 200), width=4*s)
    
    return apply_die_cut_and_shadow(downsample(im))

# ==============================================================================
# VINTAGE AND GRUNGE ARTWORK
# ==============================================================================
def draw_vintage_35mm_film(w=360, h=200):
    im, s = supersampled_canvas(w, h)
    d = ImageDraw.Draw(im)
    
    # Black film base
    d.rounded_rectangle([25*s, 25*s, 335*s, 175*s], radius=6*s, fill=(20, 22, 25, 255))
    
    # Top & bottom sprocket holes
    sprocket_col = (255, 255, 255, 0) # Transparent holes
    for i in range(11):
        sx = 35*s + i * 28*s
        d.rounded_rectangle([sx, 32*s, sx + 14*s, 46*s], radius=2*s, fill=(0, 0, 0, 0))
        d.rounded_rectangle([sx, 154*s, sx + 14*s, 168*s], radius=2*s, fill=(0, 0, 0, 0))
        
    # Frames (2 frames side by side)
    frame_col = (45, 50, 58, 255)
    d.rectangle([45*s, 56*s, 175*s, 144*s], fill=frame_col)
    d.rectangle([185*s, 56*s, 315*s, 144*s], fill=frame_col)
    
    # Golden Kodak/Fuji style frame numbers
    font = get_font(10*s, bold=True)
    d.text((110*s, 49*s), "▶ 24A", font=font, fill=(235, 180, 50, 255), anchor="mm")
    d.text((250*s, 49*s), "▶ 25", font=font, fill=(235, 180, 50, 255), anchor="mm")
    
    return apply_die_cut_and_shadow(downsample(im), outline_width=4)

def draw_vintage_stamp(w=260, h=300):
    im, s = supersampled_canvas(w, h)
    d = ImageDraw.Draw(im)
    
    # Perforated edges on ivory stamp
    d.rectangle([30*s, 30*s, 230*s, 270*s], fill=(250, 245, 235, 255))
    
    # Perforation scallops along perimeter
    perf_col = (0, 0, 0, 0)
    for x in range(35, 230, 16):
        d.ellipse([(x-5)*s, 25*s, (x+5)*s, 35*s], fill=perf_col)
        d.ellipse([(x-5)*s, 265*s, (x+5)*s, 275*s], fill=perf_col)
    for y in range(35, 270, 16):
        d.ellipse([25*s, (y-5)*s, 35*s, (y+5)*s], fill=perf_col)
        d.ellipse([225*s, (y-5)*s, 235*s, (y+5)*s], fill=perf_col)
        
    # Inner engraved frame
    d.rectangle([45*s, 45*s, 215*s, 255*s], outline=(160, 60, 70, 255), width=2*s)
    d.rectangle([52*s, 52*s, 208*s, 248*s], fill=(245, 230, 232, 255))
    
    # Botanical engraving in center
    cx, cy = 130*s, 140*s
    d.ellipse([(cx-35*s), (cy-35*s), (cx+35*s), (cy+35*s)], fill=(160, 60, 70, 255))
    d.polygon([(cx-25*s), cy, (cx+25*s), cy, cx, (cy-30*s)], fill=(255, 255, 255, 255))
    
    # Stamp denomination & airmail text
    font_bold = get_font(18*s, bold=True)
    font_sm = get_font(10*s, bold=True)
    d.text((130*s, 70*s), "POSTAGE", font=font_sm, fill=(160, 60, 70, 255), anchor="mm")
    d.text((130*s, 225*s), "25 ¢", font=font_bold, fill=(160, 60, 70, 255), anchor="mm")
    
    return apply_die_cut_and_shadow(downsample(im))

def draw_vintage_wax_seal(w=260, h=260):
    im, s = supersampled_canvas(w, h)
    d = ImageDraw.Draw(im)
    
    cx, cy = 130*s, 130*s
    crimson = (165, 25, 35, 255)
    dark_crimson = (120, 15, 25, 255)
    
    # Organic melted rim with lobes
    d.ellipse([(cx - 95*s), (cy - 90*s), (cx + 90*s), (cy + 95*s)], fill=dark_crimson)
    for ang in range(0, 360, 45):
        rad = math.radians(ang)
        lx = cx + math.cos(rad) * 80*s
        ly = cy + math.sin(rad) * 80*s
        d.ellipse([(lx - 25*s), (ly - 25*s), (lx + 25*s), (ly + 25*s)], fill=crimson)
        
    # Embossed circular center
    d.ellipse([(cx - 65*s), (cy - 65*s), (cx + 65*s), (cy + 65*s)], fill=crimson, outline=(195, 45, 55, 255), width=3*s)
    
    # Crest motif: Fleur-de-lis / botanical leaf
    d.ellipse([(cx - 15*s), (cy - 35*s), (cx + 15*s), (cy + 25*s)], fill=(130, 20, 30, 255))
    d.arc([(cx - 35*s), (cy - 15*s), cx, (cy + 25*s)], 180, 360, fill=(130, 20, 30, 255), width=6*s)
    d.arc([cx, (cy - 15*s), (cx + 35*s), (cy + 25*s)], 180, 360, fill=(130, 20, 30, 255), width=6*s)
    
    return apply_die_cut_and_shadow(downsample(im))

def draw_vintage_paperclip(w=160, h=300):
    im, s = supersampled_canvas(w, h)
    d = ImageDraw.Draw(im)
    
    # Shiny metallic chrome paperclip at slight angle
    metal = (195, 205, 215, 255)
    dark_metal = (110, 120, 130, 255)
    
    # Outer loop
    d.line([(55*s, 70*s), (55*s, 220*s)], fill=metal, width=10*s)
    d.arc([55*s, 190*s, 105*s, 250*s], 0, 180, fill=metal, width=10*s)
    d.line([(105*s, 70*s), (105*s, 220*s)], fill=metal, width=10*s)
    d.arc([55*s, 40*s, 105*s, 100*s], 180, 360, fill=metal, width=10*s)
    
    # Inner loop
    d.line([(75*s, 70*s), (75*s, 180*s)], fill=metal, width=8*s)
    d.arc([75*s, 150*s, 105*s, 200*s], 0, 180, fill=metal, width=8*s)
    
    return apply_die_cut_and_shadow(downsample(im), outline_width=4)

def draw_vintage_receipt(w=260, h=360):
    im, s = supersampled_canvas(w, h)
    d = ImageDraw.Draw(im)
    
    # Thermal paper receipt with zigzag torn top
    d.rectangle([30*s, 45*s, 230*s, 325*s], fill=(255, 252, 246, 255), outline=(225, 220, 210, 255), width=2*s)
    # Zigzag top edge
    for i in range(8):
        zx = 30*s + i * 25*s
        d.polygon([(zx, 45*s), (zx + 12*s, 32*s), (zx + 25*s, 45*s)], fill=(255, 252, 246, 255))
        
    font_bold = get_font(16*s, bold=True)
    font_mono = get_font(11*s, bold=False)
    
    d.text((130*s, 75*s), "CAFÉ SCRAPBOOK", font=font_bold, fill=(45, 45, 45, 255), anchor="mm")
    d.text((130*s, 95*s), "10/19/2024  09:42 AM", font=font_mono, fill=(100, 100, 100, 255), anchor="mm")
    d.line([(45*s, 115*s), (215*s, 115*s)], fill=(200, 200, 200, 255), width=2*s)
    
    d.text((50*s, 135*s), "1x ICED MATCHA", font=font_mono, fill=(50, 50, 50, 255))
    d.text((210*s, 135*s), "$6.50", font=font_mono, fill=(50, 50, 50, 255), anchor="ra")
    
    d.text((50*s, 160*s), "1x BUTTER CROISSANT", font=font_mono, fill=(50, 50, 50, 255))
    d.text((210*s, 160*s), "$4.75", font=font_mono, fill=(50, 50, 50, 255), anchor="ra")
    
    d.line([(45*s, 190*s), (215*s, 190*s)], fill=(200, 200, 200, 255), width=2*s)
    d.text((50*s, 210*s), "TOTAL", font=font_bold, fill=(30, 30, 30, 255))
    d.text((210*s, 210*s), "$11.25", font=font_bold, fill=(30, 30, 30, 255), anchor="ra")
    
    # Barcode
    for bx in range(50, 210, 5):
        bw = 2 if bx % 3 == 0 else 3
        d.line([(bx*s, 245*s), (bx*s, 290*s)], fill=(40, 40, 40, 255), width=bw*s)
        
    return apply_die_cut_and_shadow(downsample(im))

# ==============================================================================
# MAIN COMPILER & CATALOG GENERATOR
# ==============================================================================
def main():
    base_assets_dir = "assets/stickers"
    os.makedirs(base_assets_dir, exist_ok=True)
    
    categories = [
        "city_life",
        "travel",
        "cafe_food",
        "girly_coquette",
        "nature",
        "fashion",
        "vintage_grunge"
    ]
    for c in categories:
        os.makedirs(os.path.join(base_assets_dir, c), exist_ok=True)
        
    catalog = []
    
    # 1. CITY LIFE
    print("Generating City Life stickers...")
    draw_city_taxi().save(os.path.join(base_assets_dir, "city_life", "yellow_cab.png"))
    draw_city_buildings().save(os.path.join(base_assets_dir, "city_life", "buildings.png"))
    draw_city_street_sign().save(os.path.join(base_assets_dir, "city_life", "street_sign.png"))
    draw_city_subway_map().save(os.path.join(base_assets_dir, "city_life", "subway_map.png"))
    draw_city_traffic_light().save(os.path.join(base_assets_dir, "city_life", "traffic_light.png"))
    draw_city_transit_ticket().save(os.path.join(base_assets_dir, "city_life", "transit_ticket.png"))
    
    catalog.extend([
        {
            "id": "city-yellow-cab",
            "name": "Vintage Yellow Taxi",
            "path": "/assets/stickers/city_life/yellow_cab.png",
            "category": "city_life",
            "theme_tags": ["city", "taxi", "cab", "transport", "new york", "urban", "street", "yellow"],
            "color_palette": ["#FCCC22", "#1E1E1E", "#FFFFFF"],
            "visual_style": "cutout_sticker",
            "recommended_use": "bottom_accent",
            "suitable_placement": { "layer_type": "sticker", "suggested_positions": ["bottom_left", "bottom_right"], "default_scale": 0.85, "z_index": 2 },
            "width": 380, "height": 240, "license": "Handcrafted Open Source"
        },
        {
            "id": "city-buildings",
            "name": "Skyline Buildings",
            "path": "/assets/stickers/city_life/buildings.png",
            "category": "city_life",
            "theme_tags": ["city", "skyline", "buildings", "architecture", "urban", "downtown", "metropolis"],
            "color_palette": ["#2D343C", "#FFE8AA", "#C36E55"],
            "visual_style": "cutout_sticker",
            "recommended_use": "bottom_backdrop",
            "suitable_placement": { "layer_type": "sticker", "suggested_positions": ["bottom_center", "seam_crossing"], "default_scale": 1.0, "z_index": 1 },
            "width": 360, "height": 360, "license": "Handcrafted Open Source"
        },
        {
            "id": "city-street-sign",
            "name": "Broadway & 5th Ave Sign",
            "path": "/assets/stickers/city_life/street_sign.png",
            "category": "city_life",
            "theme_tags": ["city", "street", "sign", "broadway", "avenue", "corner", "urban", "new york"],
            "color_palette": ["#186238", "#FFFFFF", "#464B50"],
            "visual_style": "cutout_sticker",
            "recommended_use": "top_corner_accent",
            "suitable_placement": { "layer_type": "sticker", "suggested_positions": ["top_left", "top_right"], "default_scale": 0.8, "z_index": 2 },
            "width": 360, "height": 260, "license": "Handcrafted Open Source"
        },
        {
            "id": "city-subway-map",
            "name": "Metro Transit Map",
            "path": "/assets/stickers/city_life/subway_map.png",
            "category": "city_life",
            "theme_tags": ["city", "subway", "metro", "map", "transit", "train", "underground"],
            "color_palette": ["#FAF6EE", "#EE3524", "#0078D2"],
            "visual_style": "cutout_sticker",
            "recommended_use": "polaroid_backing",
            "suitable_placement": { "layer_type": "sticker", "suggested_positions": ["center_left", "bottom_right"], "default_scale": 0.9, "z_index": 1 },
            "width": 340, "height": 340, "license": "Handcrafted Open Source"
        },
        {
            "id": "city-traffic-light",
            "name": "Street Traffic Light",
            "path": "/assets/stickers/city_life/traffic_light.png",
            "category": "city_life",
            "theme_tags": ["city", "traffic", "light", "signals", "crosswalk", "urban", "stop"],
            "color_palette": ["#23262A", "#F5372D", "#28D26E"],
            "visual_style": "cutout_sticker",
            "recommended_use": "side_column_accent",
            "suitable_placement": { "layer_type": "sticker", "suggested_positions": ["top_right", "top_left"], "default_scale": 0.75, "z_index": 2 },
            "width": 200, "height": 380, "license": "Handcrafted Open Source"
        },
        {
            "id": "city-transit-ticket",
            "name": "Vintage Transit Ticket",
            "path": "/assets/stickers/city_life/transit_ticket.png",
            "category": "city_life",
            "theme_tags": ["city", "ticket", "transit", "bus", "pass", "vintage", "fare"],
            "color_palette": ["#FCF4E4", "#CD4137", "#2D2D2D"],
            "visual_style": "cutout_sticker",
            "recommended_use": "polaroid_clip",
            "suitable_placement": { "layer_type": "stamp", "suggested_positions": ["bottom_left", "bottom_center"], "default_scale": 0.85, "z_index": 2 },
            "width": 360, "height": 180, "license": "Handcrafted Open Source"
        },
        {
            "id": "city-rickshaw",
            "name": "Iconic Auto Rickshaw",
            "path": "/assets/navratri/rickshaw.png",
            "category": "city_life",
            "theme_tags": ["city", "rickshaw", "auto", "transport", "street", "urban", "desi"],
            "color_palette": ["#1A6538", "#F5B418", "#1E1E1E"],
            "visual_style": "photorealistic",
            "recommended_use": "bottom_accent",
            "suitable_placement": { "layer_type": "sticker", "suggested_positions": ["bottom_left", "bottom_right"], "default_scale": 0.8, "z_index": 2 },
            "width": 320, "height": 260, "license": "Curated Open Asset"
        }
    ])
    
    # 2. TRAVEL
    print("Generating Travel stickers...")
    draw_travel_camera().save(os.path.join(base_assets_dir, "travel", "vintage_camera.png"))
    draw_travel_postcard().save(os.path.join(base_assets_dir, "travel", "airmail_postcard.png"))
    draw_travel_suitcase().save(os.path.join(base_assets_dir, "travel", "leather_suitcase.png"))
    draw_travel_passport_stamp().save(os.path.join(base_assets_dir, "travel", "passport_stamp.png"))
    draw_travel_location_pin().save(os.path.join(base_assets_dir, "travel", "location_pin.png"))
    
    catalog.extend([
        {
            "id": "travel-vintage-camera",
            "name": "Vintage 35mm Camera",
            "path": "/assets/stickers/travel/vintage_camera.png",
            "category": "travel",
            "theme_tags": ["travel", "camera", "photo", "polaroid", "35mm", "vintage", "memories", "lens"],
            "color_palette": ["#232428", "#D7DCE2", "#E63C32"],
            "visual_style": "cutout_sticker",
            "recommended_use": "hero_accent",
            "suitable_placement": { "layer_type": "sticker", "suggested_positions": ["top_left", "bottom_right"], "default_scale": 0.85, "z_index": 2 },
            "width": 360, "height": 280, "license": "Handcrafted Open Source"
        },
        {
            "id": "travel-airmail-postcard",
            "name": "Airmail Postcard",
            "path": "/assets/stickers/travel/airmail_postcard.png",
            "category": "travel",
            "theme_tags": ["travel", "postcard", "airmail", "letter", "stamp", "postage", "wanderlust"],
            "color_palette": ["#FCF8F0", "#E13732", "#2D5FB9"],
            "visual_style": "cutout_sticker",
            "recommended_use": "photo_backing",
            "suitable_placement": { "layer_type": "frame", "suggested_positions": ["center_left", "center_right"], "default_scale": 0.9, "z_index": 1 },
            "width": 360, "height": 250, "license": "Handcrafted Open Source"
        },
        {
            "id": "travel-leather-suitcase",
            "name": "Vintage Leather Trunk",
            "path": "/assets/stickers/travel/leather_suitcase.png",
            "category": "travel",
            "theme_tags": ["travel", "suitcase", "luggage", "leather", "trunk", "vacation", "trip"],
            "color_palette": ["#C37841", "#73411E", "#EBBE50"],
            "visual_style": "cutout_sticker",
            "recommended_use": "bottom_corner",
            "suitable_placement": { "layer_type": "sticker", "suggested_positions": ["bottom_left", "bottom_right"], "default_scale": 0.85, "z_index": 2 },
            "width": 360, "height": 300, "license": "Handcrafted Open Source"
        },
        {
            "id": "travel-passport-stamp",
            "name": "Entry Visa Stamp",
            "path": "/assets/stickers/travel/passport_stamp.png",
            "category": "travel",
            "theme_tags": ["travel", "passport", "stamp", "customs", "admitted", "airport", "visa"],
            "color_palette": ["#284BA5"],
            "visual_style": "stamp",
            "recommended_use": "polaroid_corner",
            "suitable_placement": { "layer_type": "stamp", "suggested_positions": ["top_right", "bottom_left"], "default_scale": 0.75, "z_index": 3 },
            "width": 300, "height": 300, "license": "Handcrafted Open Source"
        },
        {
            "id": "travel-location-pin",
            "name": "Red Map Location Pin",
            "path": "/assets/stickers/travel/location_pin.png",
            "category": "travel",
            "theme_tags": ["travel", "pin", "location", "map", "destination", "marker", "gps"],
            "color_palette": ["#EB372D", "#FFFFFF"],
            "visual_style": "cutout_sticker",
            "recommended_use": "caption_companion",
            "suitable_placement": { "layer_type": "sticker", "suggested_positions": ["top_right", "center_right"], "default_scale": 0.65, "z_index": 3 },
            "width": 200, "height": 280, "license": "Handcrafted Open Source"
        }
    ])
    
    # 3. CAFE AND FOOD
    print("Generating Cafe & Food stickers...")
    draw_cafe_latte().save(os.path.join(base_assets_dir, "cafe_food", "latte_art.png"))
    draw_cafe_croissant().save(os.path.join(base_assets_dir, "cafe_food", "croissant.png"))
    draw_cafe_cherries().save(os.path.join(base_assets_dir, "cafe_food", "cherries.png"))
    draw_cafe_matcha().save(os.path.join(base_assets_dir, "cafe_food", "matcha_latte.png"))
    
    catalog.extend([
        {
            "id": "cafe-latte-art",
            "name": "Heart Latte Art Cup",
            "path": "/assets/stickers/cafe_food/latte_art.png",
            "category": "cafe_food",
            "theme_tags": ["cafe", "coffee", "latte", "espresso", "morning", "heart", "cozy", "drink"],
            "color_palette": ["#A0643C", "#DC9B82", "#FCF6EE"],
            "visual_style": "cutout_sticker",
            "recommended_use": "polaroid_side_accent",
            "suitable_placement": { "layer_type": "sticker", "suggested_positions": ["bottom_right", "top_left"], "default_scale": 0.8, "z_index": 2 },
            "width": 320, "height": 320, "license": "Handcrafted Open Source"
        },
        {
            "id": "cafe-croissant",
            "name": "Golden Butter Croissant",
            "path": "/assets/stickers/cafe_food/croissant.png",
            "category": "cafe_food",
            "theme_tags": ["cafe", "croissant", "pastry", "bakery", "breakfast", "french", "food"],
            "color_palette": ["#EBAA46", "#C37323"],
            "visual_style": "cutout_sticker",
            "recommended_use": "bottom_accent",
            "suitable_placement": { "layer_type": "sticker", "suggested_positions": ["bottom_left", "bottom_center"], "default_scale": 0.85, "z_index": 2 },
            "width": 360, "height": 260, "license": "Handcrafted Open Source"
        },
        {
            "id": "cafe-cherries",
            "name": "Glossy Fresh Cherries",
            "path": "/assets/stickers/cafe_food/cherries.png",
            "category": "cafe_food",
            "theme_tags": ["cafe", "cherries", "fruit", "summer", "sweet", "red", "berry"],
            "color_palette": ["#C3142D", "#559137"],
            "visual_style": "cutout_sticker",
            "recommended_use": "corner_sparkle",
            "suitable_placement": { "layer_type": "sticker", "suggested_positions": ["top_right", "bottom_right"], "default_scale": 0.75, "z_index": 2 },
            "width": 300, "height": 300, "license": "Handcrafted Open Source"
        },
        {
            "id": "cafe-matcha",
            "name": "Iced Matcha Latte",
            "path": "/assets/stickers/cafe_food/matcha_latte.png",
            "category": "cafe_food",
            "theme_tags": ["cafe", "matcha", "iced latte", "green tea", "drink", "refreshing", "cafe date"],
            "color_palette": ["#73A550", "#FCFAF5"],
            "visual_style": "cutout_sticker",
            "recommended_use": "side_accent",
            "suitable_placement": { "layer_type": "sticker", "suggested_positions": ["bottom_right", "top_right"], "default_scale": 0.75, "z_index": 2 },
            "width": 240, "height": 360, "license": "Handcrafted Open Source"
        },
        {
            "id": "cafe-cutting-chai",
            "name": "Cutting Masala Chai",
            "path": "/assets/navratri/chai_hand.png",
            "category": "cafe_food",
            "theme_tags": ["cafe", "chai", "tea", "cutting chai", "mehendi", "cozy", "comfort"],
            "color_palette": ["#C88750", "#7B3E20", "#FAF0E6"],
            "visual_style": "photorealistic",
            "recommended_use": "polaroid_companion",
            "suitable_placement": { "layer_type": "sticker", "suggested_positions": ["bottom_left", "center_left"], "default_scale": 0.8, "z_index": 2 },
            "width": 280, "height": 320, "license": "Curated Open Asset"
        }
    ])
    
    # 4. GIRLY AND COQUETTE
    print("Generating Girly & Coquette stickers...")
    draw_coquette_bow().save(os.path.join(base_assets_dir, "girly_coquette", "pink_bow.png"))
    draw_coquette_gingham_tape().save(os.path.join(base_assets_dir, "girly_coquette", "gingham_tape.png"))
    draw_coquette_heart_locket().save(os.path.join(base_assets_dir, "girly_coquette", "heart_locket.png"))
    draw_coquette_sparkle_heart().save(os.path.join(base_assets_dir, "girly_coquette", "sparkle_heart.png"))
    
    catalog.extend([
        {
            "id": "coquette-pink-bow",
            "name": "Silky Pink Coquette Bow",
            "path": "/assets/stickers/girly_coquette/pink_bow.png",
            "category": "girly_coquette",
            "theme_tags": ["coquette", "bow", "pink", "ribbon", "girly", "cute", "balletcore", "aesthetic"],
            "color_palette": ["#FFB9C8", "#EB91A5", "#FFFFFF"],
            "visual_style": "cutout_sticker",
            "recommended_use": "polaroid_top_clip",
            "suitable_placement": { "layer_type": "sticker", "suggested_positions": ["top_center", "top_left", "top_right"], "default_scale": 0.85, "z_index": 3 },
            "width": 360, "height": 300, "license": "Handcrafted Open Source"
        },
        {
            "id": "coquette-gingham-tape",
            "name": "Pink Gingham Washi Tape",
            "path": "/assets/stickers/girly_coquette/gingham_tape.png",
            "category": "girly_coquette",
            "theme_tags": ["coquette", "tape", "gingham", "washi", "plaid", "pink", "checkered"],
            "color_palette": ["#FFEBF0", "#FFAFC3"],
            "visual_style": "tape",
            "recommended_use": "polaroid_tape_strip",
            "suitable_placement": { "layer_type": "tape", "suggested_positions": ["top_left", "top_right", "bottom_center"], "default_scale": 0.9, "z_index": 3 },
            "width": 380, "height": 160, "license": "Handcrafted Open Source"
        },
        {
            "id": "coquette-heart-locket",
            "name": "Vintage Gold Heart Locket",
            "path": "/assets/stickers/girly_coquette/heart_locket.png",
            "category": "girly_coquette",
            "theme_tags": ["coquette", "heart", "locket", "gold", "jewelry", "romantic", "love", "vintage"],
            "color_palette": ["#EBB94B", "#C38C2D"],
            "visual_style": "cutout_sticker",
            "recommended_use": "accent_pendant",
            "suitable_placement": { "layer_type": "sticker", "suggested_positions": ["top_left", "bottom_right"], "default_scale": 0.75, "z_index": 2 },
            "width": 280, "height": 280, "license": "Handcrafted Open Source"
        },
        {
            "id": "coquette-sparkle-heart",
            "name": "Sparkle Candy Heart",
            "path": "/assets/stickers/girly_coquette/sparkle_heart.png",
            "category": "girly_coquette",
            "theme_tags": ["coquette", "heart", "sparkle", "stars", "glitter", "girly", "crush"],
            "color_palette": ["#FF8CAF", "#FFEB78"],
            "visual_style": "cutout_sticker",
            "recommended_use": "corner_accent",
            "suitable_placement": { "layer_type": "sticker", "suggested_positions": ["top_right", "bottom_left"], "default_scale": 0.7, "z_index": 2 },
            "width": 280, "height": 280, "license": "Handcrafted Open Source"
        }
    ])
    
    # 5. NATURE
    print("Generating Nature stickers...")
    draw_nature_butterfly().save(os.path.join(base_assets_dir, "nature", "monarch_butterfly.png"))
    draw_nature_daisy().save(os.path.join(base_assets_dir, "nature", "white_daisy.png"))
    draw_nature_ginkgo().save(os.path.join(base_assets_dir, "nature", "ginkgo_leaf.png"))
    
    catalog.extend([
        {
            "id": "nature-monarch-butterfly",
            "name": "Monarch Butterfly",
            "path": "/assets/stickers/nature/monarch_butterfly.png",
            "category": "nature",
            "theme_tags": ["nature", "butterfly", "monarch", "wings", "botanical", "spring", "insects"],
            "color_palette": ["#F5781E", "#19191E", "#FFFFFF"],
            "visual_style": "cutout_sticker",
            "recommended_use": "polaroid_corner_perch",
            "suitable_placement": { "layer_type": "sticker", "suggested_positions": ["top_left", "top_right"], "default_scale": 0.8, "z_index": 3 },
            "width": 360, "height": 300, "license": "Handcrafted Open Source"
        },
        {
            "id": "nature-white-daisy",
            "name": "Fresh White Daisy",
            "path": "/assets/stickers/nature/white_daisy.png",
            "category": "nature",
            "theme_tags": ["nature", "daisy", "flower", "bloom", "floral", "spring", "botanical", "white"],
            "color_palette": ["#FFFFFF", "#FFC31E"],
            "visual_style": "cutout_sticker",
            "recommended_use": "photo_corner_floral",
            "suitable_placement": { "layer_type": "sticker", "suggested_positions": ["bottom_left", "bottom_right"], "default_scale": 0.75, "z_index": 2 },
            "width": 300, "height": 300, "license": "Handcrafted Open Source"
        },
        {
            "id": "nature-ginkgo-leaf",
            "name": "Golden Ginkgo Leaf",
            "path": "/assets/stickers/nature/ginkgo_leaf.png",
            "category": "nature",
            "theme_tags": ["nature", "ginkgo", "leaf", "autumn", "botanical", "gold", "fall"],
            "color_palette": ["#EBB432", "#B48228"],
            "visual_style": "cutout_sticker",
            "recommended_use": "botanical_corner",
            "suitable_placement": { "layer_type": "sticker", "suggested_positions": ["top_left", "bottom_left"], "default_scale": 0.8, "z_index": 2 },
            "width": 300, "height": 300, "license": "Handcrafted Open Source"
        },
        {
            "id": "nature-pink-lotus",
            "name": "Sacred Indian Pink Lotus",
            "path": "/assets/navratri/pink_lotus.png",
            "category": "nature",
            "theme_tags": ["nature", "lotus", "pink lotus", "flower", "sacred", "blossom", "botanical"],
            "color_palette": ["#FF82A0", "#D2285A", "#FAF0F0"],
            "visual_style": "photorealistic",
            "recommended_use": "corner_bloom",
            "suitable_placement": { "layer_type": "sticker", "suggested_positions": ["bottom_right", "top_right"], "default_scale": 0.85, "z_index": 2 },
            "width": 320, "height": 320, "license": "Curated Open Asset"
        },
        {
            "id": "nature-marigold-flower",
            "name": "Fresh Marigold Bloom",
            "path": "/assets/navratri/marigold_flower.png",
            "category": "nature",
            "theme_tags": ["nature", "marigold", "genda", "flower", "orange", "festive", "botanical"],
            "color_palette": ["#F5821E", "#FFB41E"],
            "visual_style": "photorealistic",
            "recommended_use": "photo_corner",
            "suitable_placement": { "layer_type": "sticker", "suggested_positions": ["top_left", "bottom_left"], "default_scale": 0.8, "z_index": 2 },
            "width": 300, "height": 300, "license": "Curated Open Asset"
        },
        {
            "id": "nature-marigold-garland",
            "name": "Marigold Floral Garland",
            "path": "/assets/navratri/marigold_garland.png",
            "category": "nature",
            "theme_tags": ["nature", "garland", "marigold", "floral border", "toran", "flowers"],
            "color_palette": ["#F5821E", "#E65A14", "#F5D232"],
            "visual_style": "photorealistic",
            "recommended_use": "top_hanging_border",
            "suitable_placement": { "layer_type": "border", "suggested_positions": ["top_center", "seam_crossing"], "default_scale": 1.0, "z_index": 2 },
            "width": 420, "height": 180, "license": "Curated Open Asset"
        },
        {
            "id": "nature-jasmine-gajra",
            "name": "Fragrant Mogra Gajra",
            "path": "/assets/navratri/jasmine_gajra.png",
            "category": "nature",
            "theme_tags": ["nature", "jasmine", "mogra", "gajra", "garland", "white flower", "fragrance"],
            "color_palette": ["#FFFFFF", "#E8F0E5"],
            "visual_style": "photorealistic",
            "recommended_use": "photo_drape",
            "suitable_placement": { "layer_type": "sticker", "suggested_positions": ["top_right", "bottom_right"], "default_scale": 0.85, "z_index": 2 },
            "width": 340, "height": 260, "license": "Curated Open Asset"
        }
    ])
    
    # 6. FASHION
    print("Generating Fashion stickers...")
    draw_fashion_handbag().save(os.path.join(base_assets_dir, "fashion", "quilted_handbag.png"))
    draw_fashion_sunglasses().save(os.path.join(base_assets_dir, "fashion", "sunglasses.png"))
    draw_fashion_lipstick().save(os.path.join(base_assets_dir, "fashion", "red_lipstick.png"))
    
    catalog.extend([
        {
            "id": "fashion-quilted-handbag",
            "name": "Quilted Leather Handbag",
            "path": "/assets/stickers/fashion/quilted_handbag.png",
            "category": "fashion",
            "theme_tags": ["fashion", "handbag", "purse", "quilted", "leather", "luxury", "outfit", "accessories"],
            "color_palette": ["#1E2023", "#E6BE50"],
            "visual_style": "cutout_sticker",
            "recommended_use": "bottom_accent",
            "suitable_placement": { "layer_type": "sticker", "suggested_positions": ["bottom_right", "bottom_left"], "default_scale": 0.85, "z_index": 2 },
            "width": 320, "height": 300, "license": "Handcrafted Open Source"
        },
        {
            "id": "fashion-sunglasses",
            "name": "Tortoiseshell Sunglasses",
            "path": "/assets/stickers/fashion/sunglasses.png",
            "category": "fashion",
            "theme_tags": ["fashion", "sunglasses", "shades", "tortoiseshell", "chic", "summer", "eyewear"],
            "color_palette": ["#6E3719", "#232830"],
            "visual_style": "cutout_sticker",
            "recommended_use": "photo_perch",
            "suitable_placement": { "layer_type": "sticker", "suggested_positions": ["top_left", "center_right"], "default_scale": 0.8, "z_index": 3 },
            "width": 360, "height": 180, "license": "Handcrafted Open Source"
        },
        {
            "id": "fashion-lipstick",
            "name": "Classic Crimson Lipstick",
            "path": "/assets/stickers/fashion/red_lipstick.png",
            "category": "fashion",
            "theme_tags": ["fashion", "lipstick", "makeup", "beauty", "cosmetics", "red", "gold"],
            "color_palette": ["#D2192D", "#EBB94B", "#1C1E20"],
            "visual_style": "cutout_sticker",
            "recommended_use": "corner_glam",
            "suitable_placement": { "layer_type": "sticker", "suggested_positions": ["bottom_left", "bottom_right"], "default_scale": 0.75, "z_index": 2 },
            "width": 180, "height": 340, "license": "Handcrafted Open Source"
        },
        {
            "id": "fashion-jhumka-earrings",
            "name": "Lotus Filigree Jhumkas",
            "path": "/assets/navratri/lotus_jhumka_hd.png",
            "category": "fashion",
            "theme_tags": ["fashion", "jhumka", "earrings", "jewelry", "filigree", "silver", "traditional"],
            "color_palette": ["#D7DCE0", "#FF6B8B", "#B49632"],
            "visual_style": "photorealistic",
            "recommended_use": "hanging_earring_accent",
            "suitable_placement": { "layer_type": "sticker", "suggested_positions": ["top_right", "top_left"], "default_scale": 0.8, "z_index": 3 },
            "width": 260, "height": 340, "license": "Curated Open Asset"
        },
        {
            "id": "fashion-embroidered-juttis",
            "name": "Zardozi Royal Juttis",
            "path": "/assets/navratri/embroidered_juttis.png",
            "category": "fashion",
            "theme_tags": ["fashion", "juttis", "mojri", "shoes", "zardozi", "gold", "footwear"],
            "color_palette": ["#B41E28", "#E6BE50"],
            "visual_style": "photorealistic",
            "recommended_use": "bottom_corner_shoes",
            "suitable_placement": { "layer_type": "sticker", "suggested_positions": ["bottom_center", "bottom_right"], "default_scale": 0.85, "z_index": 2 },
            "width": 340, "height": 260, "license": "Curated Open Asset"
        }
    ])
    
    # 7. VINTAGE AND GRUNGE
    print("Generating Vintage & Grunge stickers...")
    draw_vintage_35mm_film().save(os.path.join(base_assets_dir, "vintage_grunge", "film_strip.png"))
    draw_vintage_stamp().save(os.path.join(base_assets_dir, "vintage_grunge", "postage_stamp.png"))
    draw_vintage_wax_seal().save(os.path.join(base_assets_dir, "vintage_grunge", "wax_seal.png"))
    draw_vintage_paperclip().save(os.path.join(base_assets_dir, "vintage_grunge", "silver_paperclip.png"))
    draw_vintage_receipt().save(os.path.join(base_assets_dir, "vintage_grunge", "cafe_receipt.png"))
    
    catalog.extend([
        {
            "id": "vintage-35mm-film",
            "name": "35mm Negative Filmstrip",
            "path": "/assets/stickers/vintage_grunge/film_strip.png",
            "category": "vintage_grunge",
            "theme_tags": ["vintage", "film", "35mm", "negative", "sprocket", "analog", "camera", "retro"],
            "color_palette": ["#141619", "#EBB432"],
            "visual_style": "cutout_sticker",
            "recommended_use": "photo_header_footer",
            "suitable_placement": { "layer_type": "frame", "suggested_positions": ["top_center", "bottom_center", "seam_crossing"], "default_scale": 1.0, "z_index": 2 },
            "width": 360, "height": 200, "license": "Handcrafted Open Source"
        },
        {
            "id": "vintage-postage-stamp",
            "name": "Engraved Postal Stamp",
            "path": "/assets/stickers/vintage_grunge/postage_stamp.png",
            "category": "vintage_grunge",
            "theme_tags": ["vintage", "stamp", "postage", "perforated", "engraving", "mail", "airmail"],
            "color_palette": ["#A03C46", "#FAF5EB"],
            "visual_style": "cutout_sticker",
            "recommended_use": "polaroid_corner_stamp",
            "suitable_placement": { "layer_type": "stamp", "suggested_positions": ["top_right", "top_left"], "default_scale": 0.75, "z_index": 3 },
            "width": 260, "height": 300, "license": "Handcrafted Open Source"
        },
        {
            "id": "vintage-wax-seal",
            "name": "Crimson Wax Seal",
            "path": "/assets/stickers/vintage_grunge/wax_seal.png",
            "category": "vintage_grunge",
            "theme_tags": ["vintage", "wax seal", "crimson", "envelope", "letter", "botanical crest", "wax"],
            "color_palette": ["#A51923", "#780F19"],
            "visual_style": "cutout_sticker",
            "recommended_use": "photo_corner_clasp",
            "suitable_placement": { "layer_type": "sticker", "suggested_positions": ["bottom_right", "top_left"], "default_scale": 0.75, "z_index": 3 },
            "width": 260, "height": 260, "license": "Handcrafted Open Source"
        },
        {
            "id": "vintage-paperclip",
            "name": "Metallic Paperclip",
            "path": "/assets/stickers/vintage_grunge/silver_paperclip.png",
            "category": "vintage_grunge",
            "theme_tags": ["vintage", "paperclip", "clip", "office", "stationery", "metal", "silver"],
            "color_palette": ["#C3CDD7", "#6E7882"],
            "visual_style": "cutout_sticker",
            "recommended_use": "photo_top_clamping",
            "suitable_placement": { "layer_type": "sticker", "suggested_positions": ["top_left", "top_center"], "default_scale": 0.65, "z_index": 4 },
            "width": 160, "height": 300, "license": "Handcrafted Open Source"
        },
        {
            "id": "vintage-cafe-receipt",
            "name": "Torn Cafe Receipt",
            "path": "/assets/stickers/vintage_grunge/cafe_receipt.png",
            "category": "vintage_grunge",
            "theme_tags": ["vintage", "receipt", "barcode", "thermal paper", "cafe", "memory", "ephemera"],
            "color_palette": ["#FFFCEF", "#2D2D2D"],
            "visual_style": "cutout_sticker",
            "recommended_use": "photo_backing_paper",
            "suitable_placement": { "layer_type": "sticker", "suggested_positions": ["bottom_left", "center_left"], "default_scale": 0.85, "z_index": 1 },
            "width": 260, "height": 360, "license": "Handcrafted Open Source"
        },
        {
            "id": "vintage-gold-jaali-frame",
            "name": "Gold Jaali Ornate Frame",
            "path": "/assets/navratri/gold_jaali_frame.png",
            "category": "vintage_grunge",
            "theme_tags": ["vintage", "frame", "gold", "jaali", "filigree", "royal", "antique"],
            "color_palette": ["#E6B432", "#C8961E"],
            "visual_style": "photorealistic",
            "recommended_use": "photo_frame",
            "suitable_placement": { "layer_type": "frame", "suggested_positions": ["center"], "default_scale": 1.0, "z_index": 2 },
            "width": 400, "height": 480, "license": "Curated Open Asset"
        },
        {
            "id": "vintage-pichwai-frame",
            "name": "Pichwai Filigree Frame",
            "path": "/assets/navratri/pichwai_filigree_frame.png",
            "category": "vintage_grunge",
            "theme_tags": ["vintage", "frame", "pichwai", "lotus", "traditional", "ornate"],
            "color_palette": ["#961E28", "#E6B432"],
            "visual_style": "photorealistic",
            "recommended_use": "photo_frame",
            "suitable_placement": { "layer_type": "frame", "suggested_positions": ["center"], "default_scale": 1.0, "z_index": 2 },
            "width": 400, "height": 480, "license": "Curated Open Asset"
        }
    ])
    
    # Save Catalog JSON
    catalog_path = "assets/stickers_catalog.json"
    with open(catalog_path, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2)
    print(f"Catalog compiled with {len(catalog)} assets -> {catalog_path}")
    
    # Sync to public/
    os.makedirs("public/assets/stickers", exist_ok=True)
    for c in categories:
        src_c = os.path.join(base_assets_dir, c)
        dst_c = os.path.join("public/assets/stickers", c)
        os.makedirs(dst_c, exist_ok=True)
        for f in os.listdir(src_c):
            shutil.copy2(os.path.join(src_c, f), os.path.join(dst_c, f))
    shutil.copy2(catalog_path, "public/assets/stickers_catalog.json")
    print("Synchronized all stickers and catalog to public/assets/")

if __name__ == "__main__":
    main()
