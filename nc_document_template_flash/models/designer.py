# -*- coding: utf-8 -*-
import base64, re, json, hashlib, logging, os, xml.etree.ElementTree as ET
from odoo import models, fields, api
from odoo.exceptions import UserError
from .jrxml_parser import JRXMLParserMixin
from .reportlab_engine import ReportLabEngineMixin

_logger = logging.getLogger(__name__)

class NCReportDesigner(models.Model, JRXMLParserMixin, ReportLabEngineMixin):
    _name = 'nc.report.designer'
    _description = 'NC Report Flash - ReportLab'
    _order = 'id desc'
    name = fields.Char(required=True, default='Reporte NC')
    model_id = fields.Many2one('ir.model', required=True, ondelete='cascade')
    model_name = fields.Char(related='model_id.model', readonly=True, store=True, string="Modelo Tecnico")
    detail_field_id = fields.Many2one('ir.model.fields', domain="[('model_id','=',model_id),('ttype','=','one2many')]")
    detail_field_name = fields.Char(related='detail_field_id.name', readonly=True)
    detail_model_id = fields.Many2one('ir.model', compute='_compute_detail_model', store=True)
    jrxml_file = fields.Binary(required=True)
    jrxml_filename = fields.Char()
    jrxml_hash = fields.Char(compute='_compute_hash', store=True)
    qweb_generated = fields.Text(readonly=True)
    cached_elements = fields.Text(readonly=True)
    page_width = fields.Integer(default=595)
    page_height = fields.Integer(default=842)
    logo_ids = fields.One2many('nc.report.designer.logo', 'designer_id')
    logo1 = fields.Binary(); logo2 = fields.Binary(); logo3 = fields.Binary()
    alias_ids = fields.One2many('nc.report.designer.field.alias', 'designer_id')
    header_alias_ids = fields.One2many('nc.report.designer.field.alias', 'designer_id', domain=[('alias_type','=','header')])
    line_alias_ids = fields.One2many('nc.report.designer.field.alias', 'designer_id', domain=[('alias_type','=','line')])
    calculated_ids = fields.One2many('nc.report.designer.calculated.field', 'designer_id')
    alias_map = fields.Text(compute='_compute_alias_map', store=True)
    header_alias_map = fields.Text(compute='_compute_alias_map', store=True)
    line_alias_map = fields.Text(compute='_compute_alias_map', store=True)
    header_fields_html = fields.Html(compute='_compute_dummy_html', sanitize=False)
    line_fields_html = fields.Html(compute='_compute_dummy_html', sanitize=False)
    available_model_fields = fields.Html(compute='_compute_available_fields', sanitize=False)
    available_params_vars = fields.Html(compute='_compute_available_params_vars', sanitize=False)
    report_view_id = fields.Many2one('ir.ui.view', readonly=True)
    report_action_id = fields.Many2one('ir.actions.report', readonly=True)
    report_xml_id = fields.Char(readonly=True)
    paperformat_id = fields.Many2one('report.paperformat', readonly=True)
    print_flash_view_id = fields.Many2one('ir.ui.view', readonly=True)
    print_button_name = fields.Char(compute="_compute_button_name", store=True, readonly=False)
    state = fields.Selection([('draft','Borrador'),('done','Generado')], default='draft')

    @api.depends('model_id')
    def _compute_button_name(self):
        for rec in self:
            if not rec.model_id:
                rec.print_button_name = "Print Flash 1"; continue
            all_recs = self.search([('model_id','=', rec.model_id.id)], order='id asc')
            ids_list = all_recs.ids
            idx = ids_list.index(rec.id)+1 if rec.id in ids_list else len(ids_list)+1
            rec.print_button_name = f"Print Flash {idx}"

    @api.depends('jrxml_file')
    def _compute_hash(self):
        for r in self:
            r.jrxml_hash = hashlib.md5(r.jrxml_file or b'').hexdigest() if r.jrxml_file else False

    @api.depends('header_alias_ids.field_id', 'header_alias_ids.jrxml_tag', 'line_alias_ids.field_id', 'line_alias_ids.jrxml_tag')
    def _compute_alias_map(self):
        for rec in self:
            def build_map(records):
                m = {}
                for a in records:
                    if not a.field_id or not a.jrxml_tag: continue
                    raw = a.jrxml_tag.strip()
                    k = raw.replace('$F{','').replace('$P{','').replace('$V{','').replace('}','').replace('"','').replace("'","").strip()
                    m[k] = a.field_id.name; m[raw] = a.field_id.name
                    m["$F{%s}" % k] = a.field_id.name; m[k.lower()] = a.field_id.name
                return m
            rec.header_alias_map = json.dumps(build_map(rec.header_alias_ids))
            rec.line_alias_map = json.dumps(build_map(rec.line_alias_ids))
            rec.alias_map = json.dumps({**json.loads(rec.header_alias_map or '{}'), **json.loads(rec.line_alias_map or '{}')})

    @api.depends('detail_field_id')
    def _compute_detail_model(self):
        for rec in self:
            if rec.detail_field_id and rec.detail_field_id.relation:
                mod = self.env['ir.model'].search([('model', '=', rec.detail_field_id.relation)], limit=1)
                rec.detail_model_id = mod.id
            else: rec.detail_model_id = False

    @api.depends('model_id')
    def _compute_dummy_html(self):
        for rec in self:
            rec.header_fields_html = '<p>OK</p>'; rec.line_fields_html = '<p>OK</p>'

    @api.depends('model_id', 'detail_model_id')
    def _compute_available_fields(self):
        for rec in self:
            rec.available_model_fields = "<div style='padding:10px;background:#e8f5e9'>Usa $P{CURRENT_DATE}, $V{PAGE_NUMBER}</div>"

    @api.depends('model_id', 'calculated_ids.jrxml_tag', 'calculated_ids.python_calc')
    def _compute_available_params_vars(self):
        for rec in self:
            calc_rows = ""
            for c in rec.calculated_ids:
                calc_rows += f"<tr style='background:#e3f2fd'><td><code>$F{{{c.jrxml_tag}}}</code></td><td>CALCULADO</td><td>{c.python_calc}</td><td>$F{{{c.jrxml_tag}}}</td></tr>"
            html = f"""
            <div style="padding:10px">
                <h4 style="color:#71639e">Parametros $P y Variables $V (No necesita mapeo)</h4>
                <p style="color:#666">Copia y pega directo en Jaspersoft Studio. Soporta $P $V $F indistintamente.</p>
                <table class="table table-sm table-bordered" style="font-size:12px">
                    <thead style="background:#f5f5f5"><tr><th>Etiqueta JRXML</th><th>Tipo</th><th>Descripcion</th><th>Ejemplo Uso</th></tr></thead>
                    <tbody>
                        <tr><td><code>$P{{{{CURRENT_DATE}}}}</code></td><td>Parametro</td><td>Fecha actual</td><td>"Fecha: " + $P{{{{CURRENT_DATE}}}}</td></tr>
                        <tr><td><code>$P{{{{CURRENT_TIME}}}}</code></td><td>Parametro</td><td>Hora actual</td><td>$P{{{{CURRENT_TIME}}}}</td></tr>
                        <tr><td><code>$P{{{{CURRENT_USER}}}}</code></td><td>Parametro</td><td>Usuario actual</td><td>$P{{{{CURRENT_USER}}}}</td></tr>
                        <tr><td><code>$P{{{{COMPANY_NAME}}}}</code></td><td>Parametro</td><td>Nombre compania</td><td>$P{{{{COMPANY_NAME}}}}</td></tr>
                        <tr><td><code>$V{{{{PAGE_NUMBER}}}}</code></td><td>Variable</td><td>Numero de pagina</td><td>"Pag " + $V{{{{PAGE_NUMBER}}}}</td></tr>
                        <tr><td><code>$V{{{{PAGE_COUNT}}}}</code></td><td>Variable</td><td>Total paginas</td><td>$V{{{{PAGE_COUNT}}}}</td></tr>
                        <tr style="background:#fff3e0"><td><code>$V{{{{REPORT_COUNT}}}}</code></td><td>Variable</td><td>Contador lineas</td><td>$V{{{{REPORT_COUNT}}}}</td></tr>
                        {calc_rows}
                    </tbody>
                </table>
            </div>
            """
            rec.available_params_vars = html

    def _get_user_now(self):
        return fields.Datetime.context_timestamp(self, fields.Datetime.now())
    def _get_user_now_str(self):
        dt = self._get_user_now()
        return dt.strftime('%d/%m/%Y %I:%M %p')
    def _get_field_value(self, obj, path, alias_map_dict=None, root_obj=None):
        if not obj or not path: return ''
        original = path.strip()
        if (original.startswith('"') and original.endswith('"')): return original[1:-1]
        mm = re.search(r'\$[FPV]\{([^}]+)\}', original)
        clean_tag = mm.group(1).strip() if mm else original.replace('$F{','').replace('$P{','').replace('$V{','').replace('}','').strip()
        path = clean_tag
        calc = self.calculated_ids.filtered(lambda c: c.jrxml_tag == clean_tag)
        if calc: return self._eval_calc_recursive(obj, calc[0].jrxml_tag, alias_map_dict, root_obj or obj)
        amap = alias_map_dict or {}
        if not amap:
            try: amap = json.loads(self.alias_map or '{}')
            except: amap = {}
        if path in amap: path = amap[path]
        path = path.replace('o.','').replace('line.','').strip()
        try:
            cur = obj
            for p in path.split('.'):
                if cur is None: return ''
                cur = getattr(cur, p, '') if hasattr(cur,p) else ''
            if hasattr(cur, '_name'): return cur.display_name or ''
            return cur if cur is not False else ''
        except: return ''
    def _get_variable_value(self, path, pdf_obj=None):
        if not path: return None
        s = str(path).strip(); m = re.search(r'\$[VPF]\{([^}]+)\}', s, re.IGNORECASE)
        var_name = m.group(1).strip().upper() if m else s.strip().upper()
        now = self._get_user_now()
        if 'CURRENT_DATE' in var_name: return now.strftime('%d/%m/%Y')
        if 'CURRENT_TIME' in var_name: return now.strftime('%H:%M:%S')
        if 'CURRENT_USER' in var_name: return self.env.user.name
        if 'COMPANY_NAME' in var_name: return self.env.company.name
        return None
    def _eval_jrxml_expression(self, expr, doc_obj, pdf_obj=None, alias_map=None, jrxml_pattern=None, root_obj=None):
        if not expr: return ''
        expr_clean = expr.replace('<![CDATA[','').replace(']]>','').strip()
        mm = re.search(r'\$[FPV]\{([^}]+)\}', expr_clean)
        if mm and self.calculated_ids.filtered(lambda c: c.jrxml_tag == mm.group(1).strip()):
            return str(self._eval_calc_recursive(doc_obj, mm.group(1).strip(), alias_map, root_obj or doc_obj))
        parts = []; cur = ''; in_q = False; q_char = ''
        for ch in expr_clean:
            if ch in ('"', "'") and not in_q: in_q=True; q_char=ch; cur+=ch
            elif ch==q_char and in_q: in_q=False; cur+=ch
            elif ch=='+' and not in_q:
                if cur.strip(): parts.append(cur.strip()); cur=''
            else: cur+=ch
        if cur.strip(): parts.append(cur.strip())
        result=''
        for token in parts:
            token=token.strip()
            if not token: continue
            if (token.startswith('"') and token.endswith('"')): result+=token[1:-1]; continue
            if '$V{' in token or '$P{' in token or '$F{' in token:
                val = self._get_variable_value(token, pdf_obj)
                if val is not None: result+=val; continue
                result+=str(self._get_field_value(doc_obj, token, alias_map or {}, root_obj or doc_obj)); continue
            result+=str(self._get_field_value(doc_obj, token, alias_map or {}, root_obj or doc_obj))
        return result.strip()
    def _eval_calc_recursive(self, obj, tag_name, alias_map_dict=None, root_obj=None, visited=None):
        if visited is None: visited = set()
        if tag_name in visited: return 0.0
        visited.add(tag_name)
        if root_obj is None: root_obj = obj
        real_by_alias = {}
        if alias_map_dict:
            for k, v in alias_map_dict.items():
                if k and v: real_by_alias[k] = v; real_by_alias[k.lower()] = v
        for a in self.line_alias_ids + self.header_alias_ids:
            if a.jrxml_tag and a.field_id:
                real_by_alias[a.jrxml_tag.strip()] = a.field_id.name
                real_by_alias[a.jrxml_tag.strip().lower()] = a.field_id.name
        calc = self.calculated_ids.filtered(lambda c: c.jrxml_tag == tag_name)
        if not calc: return 0.0
        formula = (calc[0].python_calc or '').strip()
        if not formula: return 0.0
        m_sum = re.search(r'SUM\s*\(\s*([^)]+)\s*\)', formula, re.IGNORECASE)
        if m_sum:
            inner = m_sum.group(1).strip()
            detail_field = self.detail_field_name or (self.detail_field_id.name if self.detail_field_id else False)
            lines = getattr(root_obj, detail_field, []) if detail_field else []
            total = 0.0
            for l in lines:
                if self.calculated_ids.filtered(lambda c: c.jrxml_tag == inner):
                    total += float(self._eval_calc_recursive(l, inner, alias_map_dict, root_obj, visited.copy()) or 0.0)
                else:
                    real_field = real_by_alias.get(inner, real_by_alias.get(inner.lower(), inner))
                    try:
                        v = getattr(l, real_field, 0) or 0
                        if hasattr(v, '_name'): v = 0
                        total += float(v)
                    except: pass
            rest = formula.replace(m_sum.group(0), str(total))
            try: return float(eval(rest, {"__builtins__": {}}, {"round": round, "float": float, "int": int, "sum": sum}))
            except: return float(total)
        eval_f = formula
        for other in self.calculated_ids.filtered(lambda c: c.jrxml_tag!= tag_name and c.jrxml_tag in eval_f):
            v = self._eval_calc_recursive(obj, other.jrxml_tag, alias_map_dict, root_obj, visited.copy())
            eval_f = re.sub(r'\b%s\b' % re.escape(other.jrxml_tag), str(float(v or 0)), eval_f)
        for word in re.findall(r'[a-zA-Z_][a-zA-Z0-9_]*', eval_f):
            if word.lower() in ('sum','round','float','int'): continue
            if word in [c.jrxml_tag for c in self.calculated_ids]: continue
            real_field = real_by_alias.get(word, real_by_alias.get(word.lower()))
            if not real_field and hasattr(obj, word): real_field = word
            if not real_field: continue
            try:
                if hasattr(obj, real_field):
                    v = getattr(obj, real_field, 0) or 0
                    if hasattr(v, '_name'): continue
                    eval_f = re.sub(r'\b%s\b' % re.escape(word), str(float(v or 0)), eval_f)
            except: pass
        try: return float(eval(eval_f, {"__builtins__": {}}, {"round": round, "float": float, "int": int, "sum": sum}))
        except: return 0.0

    def _create_print_flash_button(self, report_action):
        self.ensure_one()
        if self.print_flash_view_id:
            try: self.print_flash_view_id.unlink()
            except: pass
        btn_view_name = f'view_{self.model_id.model.replace(".","_")}_btn_flash_{self.id}'
        self.env['ir.ui.view'].search([('name','=',btn_view_name)]).unlink()
        label = self.print_button_name or "Print Flash"
        arch = '<data><xpath expr="//form/header" position="inside"><button name="%s" string="%s" type="action" class="oe_highlight" icon="fa-bolt" title="Imprimir Flash"/></xpath></data>' % (report_action.id, label)
        base_form = self.env['ir.ui.view'].search([('model','=',self.model_id.model),('type','=','form'),('inherit_id','=',False)], limit=1, order='priority')
        view = self.env['ir.ui.view'].create({'name': btn_view_name,'model': self.model_id.model,'inherit_id': base_form.id if base_form else False,'arch': arch,'type': 'form','priority': 99,})
        self.print_flash_view_id = view.id
        return view

    def action_convert_jrxml(self):
        self.ensure_one()
        if not self.jrxml_file: raise UserError('Sube JRXML')
        jrxml_raw = base64.b64decode(self.jrxml_file).decode('utf-8-sig', errors='ignore')
        tmp = self._clean_jrxml(jrxml_raw)
        try:
            root = ET.fromstring(tmp.encode('utf-8'))
            pw = int(root.get('pageWidth','595'))
            ph = int(root.get('pageHeight','842'))
        except: pw, ph = 595, 842
        self.page_width = pw
        self.page_height = ph
        other_elements, detail_bands = self._jrxml_to_elements(jrxml_raw)
        for band in detail_bands:
            for el in band.get('elements', []):
                if el.get('band') == 'detail' or el.get('is_detail'):
                    el['textAdjust'] = 'StretchHeight'
                    el['stretchType'] = 'RelativeToTallestObject'
                    el['positionType'] = 'Float'
                    el['isStretch'] = True
        self.cached_elements = json.dumps({'other': other_elements, 'detail_bands': detail_bands})
        def to_mm(px): return round(float(px) * 0.3527777778, 2)
        paper_vals = {'name': 'Paper %s' % self.name,'format': 'custom','page_width': to_mm(pw),'page_height': to_mm(ph),'orientation': 'Landscape' if pw > ph else 'Portrait','margin_top': 0, 'margin_bottom': 0, 'margin_left': 0, 'margin_right': 0,'header_line': False, 'header_spacing': 0, 'dpi': 96,}
        if not self.paperformat_id: self.paperformat_id = self.env['report.paperformat'].create(paper_vals).id
        else: self.paperformat_id.write(paper_vals)
        safe_name = re.sub(r'[^a-z0-9_]+', '_', self.name.lower()).strip('_') or 'report'
        xml_id_name = 'report_%s_%s' % (safe_name, self.id)
        template_name = 'nc_report_flash.%s' % xml_id_name
        full_arch = '<odoo><template id="%s"><t t-call="web.html_container"><t t-foreach="docs" t-as="o"></t></t></template></odoo>' % xml_id_name
        view_vals = {'name': template_name, 'type': 'qweb', 'arch': full_arch, 'key': template_name}
        if self.report_view_id: self.report_view_id.write(view_vals)
        else:
            self.report_view_id = self.env['ir.ui.view'].create(view_vals).id
            self.env['ir.model.data'].create({'module':'nc_report_flash','name':xml_id_name,'model':'ir.ui.view','res_id':self.report_view_id.id})
        self.report_xml_id = template_name
        report_vals = {'name': self.name, 'model': self.model_id.model, 'report_type': 'qweb-pdf', 'report_name': template_name, 'binding_model_id': self.model_id.id, 'binding_type': 'report', 'paperformat_id': self.paperformat_id.id}
        if self.report_action_id: self.report_action_id.write(report_vals)
        else: self.report_action_id = self.env['ir.actions.report'].create(report_vals).id
        self._create_print_flash_button(self.report_action_id)
        self.state = 'done'
        return {'type':'ir.actions.client','tag':'display_notification','params':{'title':'OK','message':f'Reporte {self.report_action_id.id} y Boton {self.print_button_name} creado MISMO ANCHO JRXML','type':'success'}}

    def action_delete_generated(self):
        self.ensure_one()
        if self.print_flash_view_id:
            try: self.print_flash_view_id.unlink()
            except: pass
        if self.report_xml_id:
            try:
                xml_name = self.report_xml_id.split('.')[-1]
                self.env['ir.model.data'].search([('module','=','nc_report_flash'),('name','=',xml_name)]).unlink()
            except: pass
        for f in [self.report_action_id, self.report_view_id, self.paperformat_id]:
            try: f.unlink()
            except: pass
        self.write({'report_view_id':False,'report_action_id':False,'report_xml_id':False,'paperformat_id':False,'print_flash_view_id':False,'state':'draft','cached_elements':False,'qweb_generated':False})
        return {'type':'ir.actions.client','tag':'display_notification','params':{'title':'Borrado','message':'Reporte y boton borrados','type':'warning'}}

    def unlink(self):
        for rec in self:
            try: rec.action_delete_generated()
            except: pass
        return super().unlink()

    @api.onchange('jrxml_file')
    def _onchange_jrxml_file(self):
        if self.jrxml_file:
            try:
                data = base64.b64decode(self.jrxml_file)
                self.jrxml_hash = hashlib.md5(data).hexdigest()
            except: pass