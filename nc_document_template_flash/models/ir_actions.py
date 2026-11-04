# -*- coding: utf-8 -*-
import logging
from odoo import models
_logger = logging.getLogger(__name__)
class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'
    def _render_qweb_pdf(self, report_ref, res_ids=None, data=None):
        if report_ref and 'nc_report_flash' in str(report_ref):
            try:
                designer = self.env['nc.report.designer'].search([('report_xml_id','=', report_ref)], limit=1)
                if not designer:
                    xml_name = report_ref.split('.')[-1] if '.' in report_ref else report_ref
                    designer = self.env['nc.report.designer'].search([('report_xml_id','ilike', xml_name)], limit=1)
                if designer and res_ids:
                    docs = self.env[designer.model_name].browse(res_ids)
                    if docs:
                        pdf_bytes = designer._generate_pdf_fpdf2(docs[0])
                        return pdf_bytes, 'pdf'
            except Exception as e:
                _logger.error("Flash Report error: %s" % e)
        return super()._render_qweb_pdf(report_ref, res_ids, data)