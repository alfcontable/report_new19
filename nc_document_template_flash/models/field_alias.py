# -*- coding: utf-8 -*-
from odoo import models, fields
class NCReportDesignerFieldAlias(models.Model):
    _name = 'nc.report.designer.field.alias'
    _description = 'Mapeo de Campos'
    designer_id = fields.Many2one('nc.report.designer', ondelete='cascade')
    alias_type = fields.Selection([('header','Encabezado'),('line','Linea'),('generic','Generico')], default='header', required=True, string="Tipo Alias")
    field_id = fields.Many2one('ir.model.fields', string='Campo de Odoo', ondelete='cascade', required=True)
    odoo_field_name = fields.Char(related='field_id.name', store=True, readonly=True)
    field_type = fields.Selection(related='field_id.ttype', store=True, readonly=True)
    jrxml_tag = fields.Char(string='Etiqueta en JRXML', required=True)