# -*- coding: utf-8 -*-
import re, json, os
import xml.etree.ElementTree as ET
from odoo.exceptions import UserError

class JRXMLParserMixin:

    def _get_report_dir(self):
        base = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'report'))
        if os.path.exists(base): return base
        alt = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'report'))
        if os.path.exists(alt): return alt
        try: os.makedirs(base, exist_ok=True)
        except: pass
        return base

    def _sanitize_image(self, raw_expr):
        if not raw_expr: return None, None
        raw = str(raw_expr).strip().strip('"').strip("'").replace('\\','/').strip()
        up = raw.upper()
        if 'LOGO1' in up: return 'LOGO1', 'LOGO1'
        if 'LOGO2' in up: return 'LOGO2', 'LOGO2'
        if 'LOGO3' in up: return 'LOGO3', 'LOGO3'
        if '$F{' in raw or '$P{' in raw:
            mm = re.search(r'\$\w+\{([^}]+)\}', raw)
            if mm:
                inner = mm.group(1).strip()
                if '.' in inner and inner.lower().split('.')[-1] in ('png','jpg','jpeg','gif','bmp','webp'):
                    return 'FILE', os.path.basename(inner.replace('\\','/'))
                return 'DYNAMIC', inner
        fn = os.path.basename(raw).split('?')[0].split(';')[0].strip()
        if '.' in fn and fn.lower().endswith(('.png','.jpg','.jpeg','.gif','.bmp','.webp')):
            return 'FILE', fn
        return None, None

    def _clean_jrxml(self, content):
        if not content: return content
        content = content.lstrip('\ufeff').replace('\x00','').strip()
        idx = content.find('<')
        if idx > 0: content = content[idx:]
        c = re.sub(r'<\?xml.*?\?>', '', content, flags=re.DOTALL)
        c = re.sub(r'\s+xmlns(:\w+)?="[^"]+"', '', c)
        c = re.sub(r'\s+xsi:[a-zA-Z0-9_]+="[^"]+"', '', c)
        return c.replace('xsi:schemaLocation', '')

    def _find_image_in_report(self, filename):
        if not filename: return False
        report_dir = self._get_report_dir()
        basename = os.path.basename(str(filename).replace('\\', '/').split('?')[0].split(';')[0].strip())
        if not basename: return False
        direct = os.path.join(report_dir, basename)
        if os.path.exists(direct): return direct
        if os.path.exists(report_dir):
            for root, dirs, files in os.walk(report_dir):
                for f in files:
                    if f.lower() == basename.lower():
                        return os.path.join(root, f)
        return False

    def _jrxml_to_elements(self, content):
        if isinstance(content, bytes):
            content = content.decode('utf-8-sig', errors='ignore')
        content_clean = self._clean_jrxml(content)
        try:
            root = ET.fromstring(content_clean.encode('utf-8'))
        except ET.ParseError as e:
            raise UserError(f"JRXML mal formado: {e}")

        def local(tag): return tag.split('}')[-1] if '}' in tag else tag
        def to_pt(px):
            try: return round(float(px or 0), 2)
            except: return 0.0
        def hex_to_rgb(h):
            if not h: return None
            h = h.replace('#','').strip()
            if len(h)!=6: return None
            try: return tuple(int(h[i:i+2], 16) for i in (0,2,4))
            except: return None

        left_margin = 0

        def parse_box(elem):
            box_info = {'has_border': False, 'border_width': 1, 'border_color': (0,0,0), 'top': False, 'left': False, 'bottom': False, 'right': False, 'all': False}
            for c in elem:
                if local(c.tag)=='box':
                    for pen in c:
                        ls = pen.get('lineStyle','Solid')
                        lc = pen.get('lineColor')
                        lw = pen.get('lineWidth')
                        if ls=='None': continue
                        col = hex_to_rgb(lc) if lc else None
                        if col: box_info['border_color']=col
                        if lw:
                            try: box_info['border_width']=float(lw)
                            except: pass
                        box_info['has_border']=True
                        box_info['all']=True
            for c in elem:
                if local(c.tag)=='graphicElement':
                    for pen in c:
                        if local(pen.tag)=='pen':
                            ls = pen.get('lineStyle','Solid')
                            if ls=='None': continue
                            lc = pen.get('lineColor')
                            lw = pen.get('lineWidth')
                            col = hex_to_rgb(lc) if lc else None
                            if col: box_info['border_color']=col
                            if lw:
                                try: box_info['border_width']=float(lw)
                                except: pass
                            box_info['has_border']=True
                            box_info['all']=True
            return box_info

        other_elements = []
        detail_bands = []
        sections_order = ['title','pageHeader','columnHeader','detail','columnFooter','pageFooter','summary','lastPageFooter','background']
        sections = {}
        for sec in root.iter():
            lname = local(sec.tag)
            if lname in sections_order and lname not in sections:
                sections[lname] = sec
        current_y = 0
        for sec_name in sections_order:
            sec = sections.get(sec_name)
            if sec is None: continue
            is_detail = (sec_name == 'detail')
            is_footer = sec_name in ('pageFooter','columnFooter','lastPageFooter')
            for band in sec:
                if local(band.tag)!= 'band': continue
                bh = to_pt(band.get('height','0'))
                if bh == 0: continue
                def parse_band_content(parent_elem, base_x, base_y, is_detail_flag, band_name, is_footer_flag):
                    res = []
                    for elem in parent_elem:
                        ltag = local(elem.tag)
                        if ltag in ('reportElement','box'): continue
                        rep = None
                        for child in elem:
                            if local(child.tag) == 'reportElement':
                                rep = child; break
                        if rep is None and elem.get('x') is not None: rep = elem
                        if rep is None: continue
                        x_pt = to_pt(rep.get('x','0')) + base_x + left_margin
                        y_pt = to_pt(rep.get('y','0')) + base_y
                        w_pt = to_pt(rep.get('width','100'))
                        h_pt = to_pt(rep.get('height','20'))
                        border = parse_box(elem)
                        backcolor_hex = rep.get('backcolor') or elem.get('backcolor') or ''
                        forecolor_hex = rep.get('forecolor') or elem.get('forecolor') or ''
                        mode = rep.get('mode','') or elem.get('mode','')
                        if ltag in ('rectangle','frame'):
                            bg_rgb = hex_to_rgb(backcolor_hex)
                        else:
                            bg_rgb = hex_to_rgb(backcolor_hex) if mode == 'Opaque' else None
                        fg_rgb = hex_to_rgb(forecolor_hex)
                        pattern = elem.get('pattern','') or ''
                        font_size = 9; is_bold=False; is_italic=False; align='L'
                        font_name = 'Helvetica'
                        
                        # Captura robusta de textAdjust (desde textField o textElement)
                        text_adjust = elem.get('textAdjust') or 'CutText'
                        is_stretch = False
                        position_type = rep.get('positionType', 'FixRelativeToTop')
                        stretch_type = rep.get('stretchType', 'NoStretch')
                        
                        if elem.get('isStretchWithOverflow') == 'true':
                            is_stretch = True
                            text_adjust = 'StretchHeight'
                        if rep.get('isPrintWhenDetailOverflows') == 'true':
                            is_stretch = True
                            text_adjust = 'StretchHeight'

                        for c in elem:
                            if local(c.tag) == 'textElement':
                                if c.get('textAdjust'):
                                    text_adjust = c.get('textAdjust')
                                ta = c.get('textAlignment','Left')
                                if 'Center' in ta: align='C'
                                elif 'Right' in ta: align='R'
                                for fc in c:
                                    if local(fc.tag) == 'font':
                                        try: font_size = int(float(fc.get('size','9') or 9))
                                        except: font_size = 9
                                        is_bold = fc.get('isBold','false') == 'true'
                                        is_italic = fc.get('isItalic','false') == 'true'
                        
                        if is_stretch and text_adjust == 'CutText':
                            text_adjust = 'StretchHeight'

                        common = {
                            'band':band_name,'is_detail':is_detail_flag,'is_footer':is_footer_flag,
                            'x':x_pt,'y':y_pt,'w':w_pt,'h':h_pt,
                            'bg_rgb': bg_rgb, 'fg_rgb': fg_rgb, 'font_name': font_name,
                            'size':font_size,'bold':is_bold,'italic':is_italic,'align':align,
                            'border':border,'textAdjust':text_adjust,'pattern':pattern,
                            'positionType': position_type, 'stretchType': stretch_type,
                            'isStretch': is_stretch
                        }
                        if ltag == 'staticText':
                            txt = ''
                            for cc in elem:
                                if local(cc.tag) == 'text': txt = ''.join(cc.itertext()).strip(); break
                            res.append({'type':'static','text':txt, **common})
                        elif ltag == 'textField':
                            exp_elem = None
                            for cc in elem:
                                if local(cc.tag) == 'textFieldExpression': exp_elem = cc; break
                            expr = ''.join(exp_elem.itertext()).strip() if exp_elem is not None else ''
                            if not expr: continue
                            res.append({'type':'field','raw':expr, **common})
                        elif ltag == 'image':
                            exp_elem = None
                            for cc in elem:
                                if local(cc.tag) == 'imageExpression': exp_elem = cc; break
                            expr = ''.join(exp_elem.itertext()).strip() if exp_elem is not None else ''
                            kind, fname = self._sanitize_image(expr)
                            scale_image = elem.get('scaleImage', 'RetainShape')
                            common['scaleImage'] = scale_image
                            res.append({'type':'image', 'kind': kind, 'fname': fname, **common})
                        elif ltag == 'line':
                            line_color = (0,0,0); line_width = 0.5
                            for cc in elem:
                                if local(cc.tag) == 'reportElement' and cc.get('forecolor'):
                                    lc = hex_to_rgb(cc.get('forecolor'))
                                    if lc: line_color = lc
                                if local(cc.tag) == 'graphicElement':
                                    for pen in cc:
                                        if local(pen.tag) == 'pen':
                                            if pen.get('lineColor'):
                                                lc = hex_to_rgb(pen.get('lineColor'))
                                                if lc: line_color = lc
                                            if pen.get('lineWidth'):
                                                try: line_width = float(pen.get('lineWidth'))
                                                except: pass
                            common['line_color'] = line_color
                            common['line_width'] = line_width
                            res.append({'type':'line', **common})
                        elif ltag in ('rectangle', 'frame'):
                            res.append({'type':'rect', **common})
                    return res
                band_base_y = 0 if is_footer else current_y
                band_elems = parse_band_content(band, 0, band_base_y, is_detail, sec_name, is_footer)
                if not band_elems: continue
                if is_detail:
                    detail_bands.append({'height': bh, 'y': band_base_y, 'elements': band_elems})
                else:
                    other_elements.extend(band_elems)
                if not is_footer:
                    current_y += bh
        return other_elements, detail_bands