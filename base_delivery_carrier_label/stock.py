# -*- coding: utf-8 -*-
##############################################################################
#
#    Authors: David BEAL <david.beal@akretion.com>
#             Sébastien BEAU <sebastien.beau@akretion.com>
#    Copyright (C) 2012-TODAY Akretion <http://www.akretion.com>.
#    Author: Yannick Vaucher <yannick.vaucher@camptocamp.com>
#    Copyright 2013 Camptocamp SA
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################
from openerp.osv import orm, fields
from openerp.tools.translate import _


class stock_picking(orm.Model):
    _inherit = 'stock.picking'

    def _get_carrier_type_selection(self, cr, uid, context=None):
        carrier_obj = self.pool.get('delivery.carrier')
        return carrier_obj._get_carrier_type_selection(cr, uid, context=context)

    _columns = {
        'carrier_id': fields.many2one(
            'delivery.carrier', 'Carrier',
            states={'done': [('readonly', True)]}),
        'carrier_type': fields.related(
            'carrier_id', 'type',
            string='Carrier type',
            readonly=True,
            type='selection',
            selection=_get_carrier_type_selection,
            help="Carrier type ('group')"),
        'carrier_code': fields.related(
            'carrier_id', 'code',
            string='Delivery Method Code',
            readonly=True,
            type='char',
            help="Delivery Method Code (from carrier)"),
        'option_ids': fields.many2many('delivery.carrier.option',
                                       string='Options'),
    }

    def generate_default_label(self, cr, uid, ids, context=None):
        """ Abstract method

        :return: (file_binary, file_type)

        """
        raise orm.except_orm(
                'Error',
                'No label is configured for selected delivery method.')

    def generate_shipping_labels(self, cr, uid, ids, context=None):
        """Generate a shipping label by default

        This method can be inherited to create specific shipping labels
        a list of label must be return as we can have multiple
        stock.tracking for a single picking representing packs

        :return: list of dict containing
           name: name to give to the attachement
           file: file as string
           file_type: string of file type like 'PDF'
           (optional)
           tracking_id: tracking_id if picking lines have tracking_id and
                        if label generator creates shipping label per
                        pack

        """
        return [self.generate_default_label(cr, uid, ids, context=None)]

    def action_generate_carrier_label(self, cr, uid, ids, context=None):
        shipping_label_obj = self.pool.get('shipping.label')

        pickings = self.browse(cr, uid, ids, context=context)

        for pick in pickings:
            shipping_labels = pick.generate_shipping_labels()
            for label in shipping_labels:
                # map types with models
                types = {'in': 'stock.picking.in',
                         'out': 'stock.picking.out',
                         'internal': 'stock.picking',
                         }
                res_model = types[pick.type]
                data = {
                    'name': label['name'],
                    'res_id': pick.id,
                    'res_model': res_model,
                    'datas': label['file'].encode('base64'),
                    'file_type': label['file_type'],
                }
                if label.get('tracking_id'):
                    data['tracking_id'] = label['tracking_id']
                context_attachment = context.copy()
                # remove default_type setted for stock_picking
                # as it would try to define default value of attachement
                if 'default_type' in context_attachment:
                    del context_attachment['default_type']
                shipping_label_obj.create(cr, uid, data, context=context_attachment)
        return True

    def carrier_id_change(self, cr, uid, ids, carrier_id, context=None):
        """ Inherit this method in your module """
        carrier_obj = self.pool.get('delivery.carrier')
        res = {}
        if carrier_id:
            carrier = carrier_obj.browse(cr, uid, carrier_id, context=context)
            # This can look useless as the field carrier_code and
            # carrier_type are related field. But it's needed to fill
            # this field for using this fields in the view. Indeed the
            # module that depend of delivery base can hide some field
            # depending of the type or the code

            default_option_ids = []
            available_option_ids = []
            for available_option in carrier.available_option_ids:
                available_option_ids.append(available_option.id)
                if available_option.state in ['default_option', 'mandatory']:
                    default_option_ids.append(available_option.id)
            res = {
                'value': {'carrier_type': carrier.type,
                          'carrier_code': carrier.code,
                          'option_ids': default_option_ids,
                          },
                'domain': {'option_ids': [('id', 'in', available_option_ids)],
                           },
            }
        return res

    def option_ids_change(self, cr, uid, ids, option_ids, carrier_id, context=None):
        carrier_obj = self.pool.get('delivery.carrier')
        res = {}
        if not carrier_id:
            return res
        carrier = carrier_obj.browse(cr, uid, carrier_id, context=context)
        for available_option in carrier.available_option_ids:
            if (available_option.state == 'mandatory'
                    and not available_option.id in option_ids[0][2]):
                res['warning'] = {
                    'title': _('User Error !'),
                    'message':  _("You can not remove a mandatory option."
                                  "\nOptions are reset to default.")
                }
                default_value = self.carrier_id_change(cr, uid, ids,
                                                       carrier_id,
                                                       context=context)
                res.update(default_value)
        return res

    def create(self, cr, uid, values, context=None):
        """ Trigger carrier_id_change on create

        To ensure options are setted on the basis of carrier_id copied from
        Sale order or defined by default.

        """
        carrier_id = values.get('carrier_id')
        if carrier_id:
            picking_obj = self.pool.get('stock.picking')
            res = picking_obj.carrier_id_change(cr, uid, [], carrier_id,
                                                context=context)
            option_ids = res.get('value', {}).get('option_ids')
            if option_ids:
                values.update(option_ids=[(6, 0, option_ids)])
        picking_id = super(stock_picking, self
                    ).create(cr, uid, values, context=context)
        return picking_id


class stock_picking_in(orm.Model):
    """ Add what isn't inherited from stock.picking """
    _inherit = 'stock.picking.in'

    def _get_carrier_type_selection(self, cr, uid, context=None):
        carrier_obj = self.pool.get('delivery.carrier')
        return carrier_obj._get_carrier_type_selection(cr, uid, context=context)

    _columns = {
        'carrier_id': fields.many2one(
            'delivery.carrier', 'Carrier',
            states={'done': [('readonly', True)]}),
        'carrier_type': fields.related(
            'carrier_id', 'type',
            string='Carrier type',
            readonly=True,
            type='selection',
            selection=_get_carrier_type_selection,
            help="Carrier type ('group')"),
        'carrier_code': fields.related(
            'carrier_id', 'code',
            string='Delivery Method Code',
            readonly=True,
            type='char',
            help="Delivery Method Code (from carrier)"),
        'option_ids': fields.many2many('delivery.carrier.option',
                                       string='Options'),
    }

    def action_generate_carrier_label(self, cr, uid, ids, context=None):
        picking_obj = self.pool.get('stock.picking')
        return picking_obj.action_generate_carrier_label(cr, uid, ids,
                                                         context=context)

    def carrier_id_change(self, cr, uid, ids, carrier_id, context=None):
        """ Call stock.picking carrier_id_change """
        picking_obj = self.pool.get('stock.picking')
        return picking_obj.carrier_id_change(cr, uid, ids,
                                             carrier_id, context=context)

    def option_ids_change(self, cr, uid, ids,
                          option_ids, carrier_id, context=None):
        """ Call stock.picking option_ids_change """
        picking_obj = self.pool.get('stock.picking')
        return picking_obj.option_ids_change(cr, uid, ids,
                                             option_ids, carrier_id,
                                             context=context)


class stock_picking_out(orm.Model):
    """ Add what isn't inherited from stock.picking """
    _inherit = 'stock.picking.out'

    def _get_carrier_type_selection(self, cr, uid, context=None):
        carrier_obj = self.pool.get('delivery.carrier')
        return carrier_obj._get_carrier_type_selection(cr, uid, context=context)

    _columns = {
        'carrier_id': fields.many2one(
            'delivery.carrier', 'Carrier',
            states={'done': [('readonly', True)]}),
        'carrier_type': fields.related(
            'carrier_id', 'type',
            string='Carrier type',
            readonly=True,
            type='selection',
            selection=_get_carrier_type_selection,
            help="Carrier type ('group')"),
        'carrier_code': fields.related(
            'carrier_id', 'code',
            string='Delivery Method Code',
            readonly=True,
            type='char',
            help="Delivery Method Code (from carrier)"),
        'option_ids': fields.many2many('delivery.carrier.option',
                                       string='Options'),
    }

    def action_generate_carrier_label(self, cr, uid, ids, context=None):
        picking_obj = self.pool.get('stock.picking')
        return picking_obj.action_generate_carrier_label(cr, uid, ids,
                                                         context=context)

    def carrier_id_change(self, cr, uid, ids, carrier_id, context=None):
        """ Inherit this method in your module """
        picking_obj = self.pool.get('stock.picking')
        return picking_obj.carrier_id_change(cr, uid, ids, carrier_id, context=context)

    def option_ids_change(self, cr, uid, ids, option_ids, carrier_id, context=None):
        picking_obj = self.pool.get('stock.picking')
        return picking_obj.option_ids_change(cr, uid, ids,
                                             option_ids, carrier_id,
                                             context=context)


class ShippingLabel(orm.Model):
    """ Child class of ir attachment to identify which are labels """
    _inherits = {'ir.attachment': 'attachment_id'}
    _name = 'shipping.label'
    _description = "Shipping Label"

    def _get_file_type_selection(self, cr, uid, context=None):
        return [('pdf', 'PDF')]

    _columns = {
        'file_type': fields.selection(_get_file_type_selection, 'File type'),
        'tracking_id': fields.many2one('stock.tracking', 'Pack'),
    }

    _defaults = {
        'file_type': 'pdf'
    }