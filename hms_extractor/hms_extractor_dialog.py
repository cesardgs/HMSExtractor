# -*- coding: utf-8 -*-
from PyQt5 import QtWidgets, uic
from PyQt5.QtWidgets import QFileDialog
import os

class HMSExtractorDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        # cargar UI corregido
        uic.loadUi(self.ui_path(), self)

        # botón para seleccionar carpeta
        self.btnBrowse.clicked.connect(self._browse_folder)

        # botones principales
        self.btnRun.clicked.connect(self.accept)
        self.btnClose.clicked.connect(self.reject)

    def ui_path(self):
        return os.path.join(
            os.path.dirname(__file__),
            'forms',
            'hms_extractor_dialog_base.ui'
        )

    def _browse_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Seleccionar carpeta del proyecto HMS", ""
        )
        if folder:
            self.lineEditFolder.setText(folder)

    def get_values(self):
        return dict(
            folder=self.lineEditFolder.text().strip(),
            basin=self.comboBasin.currentText().strip(),
            outdir=self.lineEditOut.text().strip(),
            checkLoadElements=self.checkLoadElements.isChecked(),
            checkLoadBackground=self.checkLoadBackground.isChecked()
        )
