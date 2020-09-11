# -*- coding: utf-8 -*-
"""
/***************************************************************************
    begin                :    09/09/23
    git sha              :    :%H$
    copyright            :    (C) 2020 by Yesid Polania
    email                :    yesidpol.3@gmail.com
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
import functools
import locale
import re
from qgis.PyQt.QtCore import QObject, pyqtSignal, QProcess, QEventLoop
from abc import ABCMeta, abstractmethod

from QgisModelBaker.libili2db.ili2dbutils import get_java_path, get_ili2db_bin, JavaNotFoundError
from QgisModelBaker.libqgsprojectgen.db_factory.db_simple_factory import DbSimpleFactory


class AbstractQObjectMeta(ABCMeta, type(QObject)):
    pass


class IliExecutable(QObject, metaclass=AbstractQObjectMeta):
    SUCCESS = 0
    # TODO: Insert more codes?
    ERROR = 1000
    ILI2DB_NOT_FOUND = 1001

    stdout = pyqtSignal(str)
    stderr = pyqtSignal(str)
    process_started = pyqtSignal(str)
    process_finished = pyqtSignal(int, int)

    __result = None

    def __init__(self, parent=None):
        QObject.__init__(self, parent)
        self.filename = None
        self.tool = None
        self.configuration = self._create_config()
        self.encoding = locale.getlocale()[1]

        # Lets python try to determine the default locale
        if not self.encoding:
            self.encoding = locale.getdefaultlocale()[1]

        # This might be unset
        # (https://stackoverflow.com/questions/1629699/locale-getlocale-problems-on-osx)
        if not self.encoding:
            self.encoding = 'UTF8'

    @abstractmethod
    def _create_config(self):
        pass

    @abstractmethod
    def _get_done_pattern(self):
        pass

    def _get_ili2db_version(self):
        return self.configuration.db_ili_version

    def _args(self, hide_password):
        self.configuration.tool = self.tool
        db_simple_factory = DbSimpleFactory()
        db_factory = db_simple_factory.create_factory(self.tool)

        config_manager = db_factory.get_db_command_config_manager(self.configuration)

        return config_manager.get_ili2db_args(hide_password)

    def command(self, hide_password):
        ili2db_bin = get_ili2db_bin(self.tool, self._get_ili2db_version(), self.stdout, self.stderr)
        if not ili2db_bin:
            return self.ILI2DB_NOT_FOUND

        ili2db_jar_arg = ["-jar", ili2db_bin]

        args = self._args(hide_password)

        java_path = get_java_path(self.configuration.base_configuration)

        command_args = ili2db_jar_arg + args
        command = java_path + ' ' + ' '.join(command_args)

        return command

    def command_with_password(self, command):
        if '--dbpwd ******' in command:
            args = self._args(False)
            i = args.index('--dbpwd')
            command = command.replace('--dbpwd ******', '--dbpwd '+args[i+1])
        return command

    def command_without_password(self, command):
        regex = re.compile('--dbpwd [^ ]*')
        match = regex.match(command)
        if match:
            command = command.replace(match.group(1), '--dbpwd ******')
        return command

    def run(self, command=None):
        if not command:
            # we usually use version 4 except in case of a fallback
            command = self.command(False)

        proc = QProcess()
        proc.readyReadStandardError.connect(
            functools.partial(self.stderr_ready, proc=proc))
        proc.readyReadStandardOutput.connect(
            functools.partial(self.stdout_ready, proc=proc))

        proc.start(self.command_with_password(command))

        if not proc.waitForStarted():
            proc = None

        if not proc:
            raise JavaNotFoundError()

        self.process_started.emit(self.command_without_password(command))

        self.__result = self.ERROR

        loop = QEventLoop()
        proc.finished.connect(loop.exit)
        loop.exec()

        self.process_finished.emit(proc.exitCode(), self.__result)
        return self.__result

    def stderr_ready(self, proc):
        text = bytes(proc.readAllStandardError()).decode(self.encoding)

        done_pattern = self._get_done_pattern()

        if done_pattern.search(text):
            self.__result = self.SUCCESS

        self.stderr.emit(text)

    def stdout_ready(self, proc):
        text = bytes(proc.readAllStandardOutput()).decode(self.encoding)
        self.stdout.emit(text)
