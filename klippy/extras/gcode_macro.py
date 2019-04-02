# Add ability to define custom g-code macros
#
# Copyright (C) 2018-2019  Kevin O'Connor <kevin@koconnor.net>
#
# This file may be distributed under the terms of the GNU GPLv3 license.
import traceback, logging
import jinja2

DefaultResult = {'is_enabled': False}

class StatusWrapper:
    def __init__(self, printer, eventtime=None):
        self.printer = printer
        self.eventtime = eventtime
        self.cache = {}
    def __getitem__(self, val):
        sval = str(val).strip()
        if sval in self.cache:
            return self.cache[sval]
        po = self.printer.lookup_object(sval, None)
        if po is None or not hasattr(po, 'get_status'):
            return DefaultResult
        if self.eventtime is None:
            self.eventtime = self.printer.get_reactor().monotonic()
        self.cache[sval] = res = dict(po.get_status(self.eventtime))
        res['is_enabled'] = True
        return res

def get_template_environment(printer):
    env = printer.lookup_object("template_environment", None)
    if env is not None:
        return env
    env = jinja2.Environment('{{', '}}', '{', '}')
    printer.add_object('template_environment', env)
    return env

class GCodeMacro:
    def __init__(self, config):
        self.alias = config.get_name().split()[1].upper()
        self.printer = config.get_printer()
        script = config.get('gcode')
        env = get_template_environment(self.printer)
        try:
            self.template = env.from_string(script)
        except Exception as e:
            msg = "Error loading template %s: %s" % (
                self.alias, traceback.format_exception_only(type(e), e)[-1])
            logging.exception(msg)
            raise config.error(msg)
        self.gcode = self.printer.lookup_object('gcode')
        self.gcode.register_command(self.alias, self.cmd, desc=self.cmd_desc)
        self.in_script = False
        prefix = 'default_parameter_'
        self.kwparams = { o[len(prefix):].upper(): config.get(o)
                          for o in config.get_prefix_options(prefix) }
    cmd_desc = "G-Code macro"
    def cmd(self, params):
        if self.in_script:
            raise self.gcode.error(
                "Macro %s called recursively" % (self.alias,))
        script = ""
        kwparams = dict(self.kwparams)
        kwparams.update(params)
        kwparams['status'] = StatusWrapper(self.printer)
        try:
            script = str(self.template.render(kwparams))
        except Exception as e:
            msg = "Error evaluating %s: %s" % (
                self.alias, traceback.format_exception_only(type(e), e)[-1])
            logging.exception(msg)
            raise self.gcode.error(msg)
        self.in_script = True
        try:
            self.gcode.run_script_from_command(script)
        finally:
            self.in_script = False

def load_config_prefix(config):
    return GCodeMacro(config)
