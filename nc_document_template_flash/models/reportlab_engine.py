# -*- coding: utf-8 -*-
import io, base64, os, tempfile, json, logging, re
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.lib.colors import toColor

_logger = logging.getLogger(__name__)

class ReportLabEngineMixin:
    def _is_monetary_field(self, doc_obj, raw_tag):
        """Verifica en la configuración real de Odoo si el campo es de tipo 'monetary'."""
        if not doc_obj or not hasattr(doc_obj, '_fields'):
            return False
        original = str(raw_tag).strip()
        mm = re.search(r'\$[FPV]\{([^}]+)\}', original)
        clean_tag = mm.group(1).strip() if mm else original.replace('$F{','').replace('$P{','').replace('$V{','').replace('}','').strip()
        
        amap = {}
        try:
            amap = {**json.loads(self.header_alias_map or '{}'), **json.loads(self.line_alias_map or '{}')}
        except:
            pass
        
        field_name = amap.get(clean_tag, amap.get(clean_tag.lower(), clean_tag))
        field_name = field_name.replace('o.','').replace('line.','').strip()
        
        if field_name in doc_obj._fields:
            field_obj = doc_obj._fields[field_name]
            if getattr(field_obj, 'type', None) == 'monetary':
                return True
        return False

    def _format_number_or_currency(self, val, raw_tag='', doc_obj=None):
        """Formatea números y montos leyendo explícitamente los separadores configurados en Odoo."""
        if val is None or val is False:
            return '', False
        try:
            if isinstance(val, str):
                clean_val = val.strip()
                if not clean_val:
                    return '', False
                num = float(clean_val)
            elif isinstance(val, (int, float)):
                num = float(val)
            else:
                return str(val), False
        except (TypeError, ValueError):
            return str(val), False

        env_to_use = None
        if hasattr(self, 'env'):
            env_to_use = self.env
        elif doc_obj and hasattr(doc_obj, 'env'):
            env_to_use = doc_obj.env

        try:
            if env_to_use:
                lang_code = env_to_use.context.get('lang') or env_to_use.user.lang or 'en_US'
                lang_rec = env_to_use['res.lang']._lang_get(lang_code)
                if lang_rec:
                    base_str = f"{num:,.2f}"
                    t_sep = lang_rec.thousands_sep if lang_rec.thousands_sep is not None else ','
                    d_sep = lang_rec.decimal_point if lang_rec.decimal_point is not None else '.'
                    
                    # Aplica estrictamente los separadores de miles y decimales de Odoo
                    formatted_num = base_str.replace(',', 'X').replace('.', d_sep).replace('X', t_sep)
                else:
                    formatted_num = f"{num:,.2f}"
            else:
                formatted_num = f"{num:,.2f}"
        except Exception as e:
            _logger.warning(f"Error aplicando formato regional de Odoo: {e}")
            formatted_num = f"{num:,.2f}"

        return formatted_num, False

    def _get_variable_value_extended(self, path, pdf_obj=None, doc_obj=None):
        if not path:
            return None
        s = str(path).strip()
        m = re.search(r'\$[VPF]\{([^}]+)\}', s, re.IGNORECASE)
        var_name = m.group(1).strip().upper() if m else s.strip().upper()
        var_name = var_name.strip()
        now = None
        try:
            now = self._get_user_now()
        except:
            pass
        if var_name == 'CURRENT_DATE': return now.strftime('%d/%m/%Y') if now else '01/01/2026'
        if var_name == 'CURRENT_TIME': return now.strftime('%H:%M:%S') if now else '00:00:00'
        if var_name == 'CURRENT_YEAR': return now.strftime('%Y') if now else '2026'
        if var_name == 'CURRENT_MONTH': return now.strftime('%m') if now else '01'
        if var_name == 'CURRENT_DAY': return now.strftime('%d') if now else '01'
        if var_name == 'CURRENT_USER': 
            try: return self.env.user.name
            except: return 'Admin'
        if var_name in ('USER_LOGIN','CURRENT_USER_LOGIN'):
            try: return self.env.user.login
            except: return 'admin'
        if var_name == 'USER_EMAIL':
            try: return self.env.user.email or ''
            except: return ''
        if var_name == 'COMPANY_NAME':
            try: return self.env.company.name
            except: return 'My Company'
        if var_name == 'COMPANY_VAT':
            try: return self.env.company.vat or ''
            except: return ''
        if var_name == 'COMPANY_CITY':
            try: return self.env.company.city or ''
            except: return ''
        if var_name == 'COMPANY_STREET':
            try: return self.env.company.street or ''
            except: return ''
        if var_name == 'COMPANY_PHONE':
            try: return self.env.company.phone or ''
            except: return ''
        if var_name == 'COMPANY_EMAIL':
            try: return self.env.company.email or ''
            except: return ''
        if var_name in ('REPORT_NAME','REPORT_TITLE','JASPER_REPORT'):
            return getattr(self, 'name', 'Report')
        if var_name == 'LOGO' or var_name.startswith('LOGO'):
            return ''
        if var_name in ('REPORT_PARAMETERS_MAP','REPORT_DATA_SOURCE','REPORT_CONNECTION','REPORT_LOCALE','REPORT_TIME_ZONE','REPORT_RESOURCE_BUNDLE','REPORT_SCRIPTLET','REPORT_CONTEXT','REPORT_MAX_COUNT','REPORT_CLASS_LOADER','REPORT_VIRTUALIZER','IS_IGNORE_PAGINATION','SORT_FIELDS','FILTER','REPORT_FORMAT_FACTORY'):
            if 'LOCALE' in var_name:
                try: return self.env.context.get('lang','es_ES')
                except: return 'es_ES'
            if 'TIME_ZONE' in var_name: return 'UTC'
            if 'IGNORE_PAGINATION' in var_name: return False
            if 'MAX_COUNT' in var_name: return 0
            return ''
        if var_name == 'PAGE_NUMBER': 
            try: return str(pdf_obj.page_number if hasattr(pdf_obj,'page_number') else 1)
            except: return '1'
        if var_name in ('PAGE_COUNT','MASTER_PAGE_COUNT'):
            try: return str(pdf_obj.page_count if hasattr(pdf_obj,'page_count') else 1)
            except: return '1'
        if var_name == 'MASTER_CURRENT_PAGE':
            try: return str(pdf_obj.page_number if hasattr(pdf_obj,'page_number') else 1)
            except: return '1'
        if var_name in ('REPORT_COUNT','ROW_COUNT'):
            try: return str(pdf_obj.report_count if hasattr(pdf_obj,'report_count') else 0)
            except: return '0'
        if var_name == 'COLUMN_NUMBER': return '1'
        if var_name == 'COLUMN_COUNT': return '1'
        if var_name == 'GROUP_COUNT': return '0'
        if var_name in ('PAGE_X','PAGE_Y'): return '0'
        if var_name.startswith('GROUP_') and var_name.endswith('_COUNT'): return '0'
        return None

    def _get_variable_value(self, path, pdf_obj=None):
        val = self._get_variable_value_extended(path, pdf_obj, None)
        return val

    def _generate_pdf_fpdf2(self, doc):
        def pt2mm(pt): return pt * 0.3527777778
        other_elements = []; detail_bands = []
        if self.cached_elements:
            try:
                cached = json.loads(self.cached_elements)
                if isinstance(cached, dict) and 'detail_bands' in cached:
                    other_elements = cached.get('other', [])
                    detail_bands = cached.get('detail_bands', [])
            except: pass
        if not other_elements and not detail_bands:
            jrxml_raw = base64.b64decode(self.jrxml_file).decode('utf-8-sig', errors='ignore')
            other_elements, detail_bands = self._jrxml_to_elements(jrxml_raw)

        pw_mm = pt2mm(self.page_width or 595); ph_mm = pt2mm(self.page_height or 842)
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=(pw_mm*mm, ph_mm*mm))
        try: header_amap = json.loads(self.header_alias_map or '{}')
        except: header_amap = {}
        try: line_amap = json.loads(self.line_alias_map or '{}')
        except: line_amap = {}
        combined_alias = {**header_amap, **line_amap}
        header_elems = [e for e in other_elements if e.get('band') in ('title','pageHeader','columnHeader')]
        page_footer_elems = [e for e in other_elements if e.get('band') in ('pageFooter','lastPageFooter')]
        col_footer_elems = [e for e in other_elements if e.get('band') == 'columnFooter']
        page_footer_h_mm = pt2mm(max([e['y']+e['h'] for e in page_footer_elems], default=0)) if page_footer_elems else 0
        if page_footer_h_mm == 0: page_footer_h_mm = 15
        tmp_files = []

        def set_rgb(rgb, fill=True):
            if not rgb: return
            try:
                if isinstance(rgb, str):
                    if 'transparent' in rgb.lower(): return
                    col = toColor(rgb)
                else:
                    r,g,b = rgb[0], rgb[1], rgb[2]
                    if isinstance(r, int) and r > 1:
                        col = toColor(f"rgb({r},{g},{b})")
                    else:
                        if fill: c.setFillColorRGB(r,g,b); return
                        else: c.setStrokeColorRGB(r,g,b); return
                if fill: c.setFillColor(col)
                else: c.setStrokeColor(col)
            except: return

        def draw_box(x, y, w, h, border, bg, is_rect=False):
            if bg:
                set_rgb(bg, True)
                c.rect(x*mm, (ph_mm - y - h)*mm, w*mm, h*mm, fill=1, stroke=0)
            if is_rect:
                bc = border.get('border_color') if border else None
                if isinstance(bc, str) and 'transparent' in bc.lower(): return
                if bc is None and border and border.get('has_border') is False: return
                if not bc: bc = (0,0,0)
                bw = border.get('border_width', 1) if border else 1
                if bw <= 0: bw = 1
                c.setLineWidth(bw); set_rgb(bc, False)
                c.rect(x*mm, (ph_mm - y - h)*mm, w*mm, h*mm, fill=0, stroke=1)
                c.setLineWidth(0.5); c.setStrokeColorRGB(0,0,0); return
            if not border or border.get('has_border') is not True: return
            bc = border.get('border_color') or (0,0,0)
            if isinstance(bc, str) and 'transparent' in bc.lower(): return
            bw = border.get('border_width', 0.8)
            if bw <= 0: bw = 0.8
            c.setLineWidth(bw); set_rgb(bc, False)
            c.rect(x*mm, (ph_mm - y - h)*mm, w*mm, h*mm, fill=0, stroke=1)
            c.setLineWidth(0.5); c.setStrokeColorRGB(0,0,0)

        def render_image(el, x, y, w, h):
            fname = el.get('fname'); kind = el.get('kind'); path=False
            if fname:
                logo_rec = self.logo_ids.filtered(lambda l: l.key and l.key.upper() == str(fname).upper())
                if logo_rec and logo_rec[0].logo:
                    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.png')
                    tmp.write(base64.b64decode(logo_rec[0].logo)); tmp.close()
                    path = tmp.name; tmp_files.append(path)
            if not path and kind in ('LOGO1','LOGO2','LOGO3'):
                bin_val = getattr(self, kind.lower(), False)
                if bin_val:
                    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.png')
                    tmp.write(base64.b64decode(bin_val)); tmp.close()
                    path = tmp.name; tmp_files.append(path)
            if not path and kind == 'FILE' and fname:
                path = self._find_image_in_report(fname)
            if path and os.path.exists(path):
                try:
                    scale = el.get('scaleImage', 'RetainShape')
                    img = ImageReader(path)
                    if scale == 'FillFrame':
                        c.drawImage(img, x*mm, (ph_mm - y - h)*mm, w*mm, h*mm, preserveAspectRatio=False, mask='auto')
                    elif scale == 'Clip':
                        c.saveState()
                        p = c.beginPath()
                        p.rect(x*mm, (ph_mm - y - h)*mm, w*mm, h*mm)
                        c.clipPath(p, stroke=0, fill=0)
                        c.drawImage(img, x*mm, (ph_mm - y - h)*mm, w*mm, h*mm, preserveAspectRatio=True, anchor='nw', mask='auto')
                        c.restoreState()
                    else:
                        c.drawImage(img, x*mm, (ph_mm - y - h)*mm, w*mm, h*mm, preserveAspectRatio=True, anchor='nw', mask='auto')
                except Exception as e:
                    _logger.warning(f"No se pudo dibujar imagen {fname}: {e}")

        def calc_needed_mm(text, w, size, bold, text_adjust='CutText'):
            style = 'Helvetica-Bold' if bold else 'Helvetica'
            max_w = w*mm - 6
            if max_w < 10: max_w = 10
            
            if text_adjust == 'StretchHeight':
                lines = simpleSplit(str(text) if text else "", style, size, max_w)
                if not lines: lines = [""]
                h_mm = len(lines) * (size * 0.3527777778 * 1.15) + 1.5
                if h_mm < 5: h_mm = 5
                return h_mm
            return None

        def draw_text(x, y, w, h, text, align='L', bold=False, size=9, bg=None, fg=None, border=None, text_adjust='CutText', force_h=None):
            style = 'Helvetica-Bold' if bold else 'Helvetica'
            t = str(text) if text else ""
            max_w = w*mm - 6
            use_h = force_h if force_h else h
            
            draw_box(x, y, w, use_h, border if border and border.get('has_border') else None, bg, is_rect=False)
            if not t.strip():
                return use_h

            if fg: set_rgb(fg, True)
            else: c.setFillColorRGB(0,0,0)

            c.saveState()
            p = c.beginPath()
            p.rect(x*mm, (ph_mm - y - use_h)*mm, w*mm, use_h*mm)
            c.clipPath(p, stroke=0, fill=0)

            if text_adjust == 'StretchHeight':
                lines = simpleSplit(t, style, size, max_w)
                if not lines: lines = [""]
                c.setFont(style, size)
                cur_y = y + 1.2
                for line in lines:
                    tx = x*mm + 2
                    if align == 'C':
                        sw = stringWidth(line, style, size); tx = x*mm + (w*mm - sw)/2
                    elif align == 'R':
                        sw = stringWidth(line, style, size); tx = x*mm + w*mm - sw - 3
                    c.drawString(tx, (ph_mm - cur_y - 2.5)*mm, line)
                    cur_y += size * 0.40
            elif text_adjust == 'ScaleFont':
                cur_size = size
                while cur_size > 4 and stringWidth(t, style, cur_size) > max_w:
                    cur_size -= 0.5
                c.setFont(style, cur_size)
                tx = x*mm + 2
                if align == 'C':
                    sw = stringWidth(t, style, cur_size); tx = x*mm + (w*mm - sw)/2
                elif align == 'R':
                    sw = stringWidth(t, style, cur_size); tx = x*mm + w*mm - sw - 3
                c.drawString(tx, (ph_mm - y - use_h + 2)*mm, t)
            else:
                lines = simpleSplit(t, style, size, max_w)
                if not lines: lines = [""]
                c.setFont(style, size)
                cur_y = y + 1.2
                for line in lines:
                    tx = x*mm + 2
                    if align == 'C':
                        sw = stringWidth(line, style, size); tx = x*mm + (w*mm - sw)/2
                    elif align == 'R':
                        sw = stringWidth(line, style, size); tx = x*mm + w*mm - sw - 3
                    c.drawString(tx, (ph_mm - cur_y - 2.5)*mm, line)
                    cur_y += size * 0.40

            c.restoreState()
            c.setFillColorRGB(0,0,0)
            return use_h

        def render_band(elems, base_y, doc_obj, alias_map, root, band_abs_y=0, is_detail=False):
            rects = [e for e in elems if e['type'] == 'rect']
            others = [e for e in elems if e['type'] != 'rect']
            needed_heights = {}
            max_needed = 0
            
            for el in others:
                x = pt2mm(el['x']); w = pt2mm(el['w']); h = pt2mm(el['h'])
                if w < 2: w = 40
                if h < 2: h = 7
                text_val = ""
                if el['type'] == 'static':
                    text_val = el['text']
                elif el['type'] == 'field':
                    val = self._eval_jrxml_expression(el['raw'], doc_obj, None, alias_map, el.get('pattern',''), root_obj=root)
                    if not val and val != 0 and val != 0.0:
                        var_val = self._get_variable_value(el['raw'], None)
                        val = var_val if var_val is not None else self._get_field_value(doc_obj, el['raw'], combined_alias, root_obj=root)
                    formatted_val, _ = self._format_number_or_currency(val, el['raw'], doc_obj)
                    text_val = formatted_val
                
                t_adj = el.get('textAdjust', 'CutText')
                if text_val and t_adj == 'StretchHeight':
                    nh = calc_needed_mm(text_val, w, el.get('size',9), el.get('bold'), t_adj)
                    if nh and nh < h: nh = h
                else:
                    nh = h
                needed_heights[id(el)] = nh if nh else h
                if nh and nh > max_needed:
                    max_needed = nh
            
            if max_needed == 0:
                max_needed = pt2mm(max([e['h'] for e in others], default=10))
                
            band_used = 0
            for el in others:
                rel_y = el['y'] - band_abs_y
                x = pt2mm(el['x']); y = base_y + pt2mm(rel_y); w = pt2mm(el['w']); h = pt2mm(el['h'])
                if w < 2: w = 40
                if h < 2: h = 7
                
                t_adj = el.get('textAdjust', 'CutText')
                if t_adj == 'StretchHeight':
                    use_h = max_needed
                else:
                    use_h = h

                if el['type'] == 'static':
                    draw_text(x, y, w, h, el['text'], el.get('align','L'), el.get('bold'), el.get('size',9), el.get('bg_rgb'), el.get('fg_rgb'), el.get('border'), t_adj, force_h=use_h)
                elif el['type'] == 'field':
                    val = self._eval_jrxml_expression(el['raw'], doc_obj, None, alias_map, el.get('pattern',''), root_obj=root)
                    if not val and val != 0 and val != 0.0:
                        var_val = self._get_variable_value_extended(el['raw'], None, root)
                        if var_val is None:
                            var_val = self._get_variable_value(el['raw'], None)
                        val = var_val if var_val is not None else self._get_field_value(doc_obj, el['raw'], combined_alias, root_obj=root)
                    
                    val, _ = self._format_number_or_currency(val, el['raw'], doc_obj)
                    draw_text(x, y, w, h, val, el.get('align','L'), el.get('bold'), el.get('size',9), el.get('bg_rgb'), el.get('fg_rgb'), el.get('border'), t_adj, force_h=use_h)
                elif el['type'] == 'image':
                    draw_box(x, y, w, use_h, el.get('border'), el.get('bg_rgb'), is_rect=False)
                    render_image(el, x, y, w, use_h)
                elif el['type'] == 'line':
                    lc = el.get('line_color', (0,0,0))
                    if el.get('border',{}).get('border_color'): lc = el['border']['border_color']
                    if el.get('line_color'): lc = el['line_color']
                    lw = el.get('line_width', 0.8)
                    c.setLineWidth(lw); set_rgb(lc, False)
                    c.line(x*mm, (ph_mm - y)*mm, (x+w)*mm, (ph_mm - y)*mm)
                    c.setLineWidth(0.5); c.setStrokeColorRGB(0,0,0)
                bottom = pt2mm(rel_y) + use_h
                if bottom > band_used: band_used = bottom
            for el in rects:
                rel_y = el['y'] - band_abs_y
                x = pt2mm(el['x']); y = base_y + pt2mm(rel_y); w = pt2mm(el['w']); h = pt2mm(el['h'])
                if is_detail and max_needed > h:
                    h = max_needed
                draw_box(x, y, w, h, el.get('border'), el.get('bg_rgb'), is_rect=True)
                bottom = pt2mm(rel_y) + h
                if bottom > band_used: band_used = bottom
            return band_used if band_used else (max_needed if is_detail else pt2mm(max([e['h'] for e in elems], default=10)))

        header_used = render_band(header_elems, 0, doc, header_amap, doc, 0, is_detail=False)
        y_cur = (header_used if header_used else pt2mm(max([e['y']+e['h'] for e in header_elems], default=10))) + 1
        detail_field = self.detail_field_name or (self.detail_field_id.name if self.detail_field_id else False)
        lines = getattr(doc, detail_field, []) if detail_field else []
        for line in lines:
            for band in detail_bands:
                est_h = pt2mm(band['height'])
                if y_cur + est_h + 10 > ph_mm - page_footer_h_mm - 5:
                    render_band(page_footer_elems, ph_mm - page_footer_h_mm, doc, header_amap, doc, 0, is_detail=False)
                    c.showPage()
                    header_used = render_band(header_elems, 0, doc, header_amap, doc, 0, is_detail=False)
                    y_cur = (header_used if header_used else pt2mm(max([e['y']+e['h'] for e in header_elems], default=10))) + 1
                used_h = render_band(band['elements'], y_cur, line, line_amap, doc, band.get('y',0), is_detail=True)
                y_cur += max(pt2mm(band['height']), used_h) + 0.5
        if col_footer_elems:
            if y_cur + pt2mm(max([e['y']+e['h'] for e in col_footer_elems], default=20)) > ph_mm - page_footer_h_mm - 2:
                render_band(page_footer_elems, ph_mm - page_footer_h_mm, doc, header_amap, doc, 0, is_detail=False)
                c.showPage()
                y_cur = 10
            col_used = render_band(col_footer_elems, y_cur, doc, header_amap, doc, 0, is_detail=False)
            y_cur += col_used if col_used else pt2mm(max([e['y']+e['h'] for e in col_footer_elems], default=20))
        render_band(page_footer_elems, ph_mm - page_footer_h_mm, doc, header_amap, doc, 0, is_detail=False)
        c.showPage(); c.save()
        for tf in tmp_files:
            try: os.unlink(tf)
            except: pass
        buf.seek(0); return buf.read()