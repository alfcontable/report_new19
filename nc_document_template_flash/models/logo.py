# -*- coding: utf-8 -*-
from odoo import models, fields
class NCReportDesignerLogo(models.Model):
    _name = 'nc.report.designer.logo'
    _description = 'Logos'
    designer_id = fields.Many2one('nc.report.designer', ondelete='cascade')
    key = fields.Char(default='LOGO1', required=True)
    logo = fields.Binary(required=True)