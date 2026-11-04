# -*- coding: utf-8 -*-
from odoo import models, fields
class NCReportDesignerCalculatedField(models.Model):
    _name = 'nc.report.designer.calculated.field'
    _description = 'Campo Calculado JRXML'
    _order = 'id'
    designer_id = fields.Many2one('nc.report.designer', string="Diseñador", ondelete='cascade', required=True)
    jrxml_tag = fields.Char(string="Tag JRXML", required=True)
    python_calc = fields.Char(string="Cálculo Python", required=True)