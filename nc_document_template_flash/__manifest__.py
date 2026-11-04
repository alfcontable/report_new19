{
    'name': 'NC Report Flash - Jasper JRXML',
    'icon': '/nc_document_template_flash/static/description/icon.png',
    'version': '19.0.1.1.0',
    'price': 79.00,
    'currency':'USD',
    'support':'gtnorw@yahoo.com', 
    'summary': 'Diseñador Jasper JRXML -> QWeb para SOLO MODELOS (cualquier modelo) con panel o. y line. + boton copiar $F{}',
    'author': 'Nicacreator',
    'category': 'Reporting',
    'depends': ['base', 'web'],
    'data': [
        'security/ir.model.access.csv',
        'views/report_designer_view.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'OPL-1',
}