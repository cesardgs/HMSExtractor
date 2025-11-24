# -*- coding: utf-8 -*-
import os, shutil
from PyQt5.QtGui import QColor, QIcon
from PyQt5.QtWidgets import QAction, QMessageBox
from PyQt5.QtCore import QVariant
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsField, QgsFields, QgsFeature,
    QgsGeometry, QgsPointXY, QgsVectorFileWriter, QgsWkbTypes,
    QgsMarkerSymbol, QgsRasterMarkerSymbolLayer,
    QgsSimpleLineSymbolLayer, QgsCoordinateReferenceSystem,
    QgsPalLayerSettings, QgsVectorLayerSimpleLabeling, QgsTextFormat
)
from .hms_extractor_dialog import HMSExtractorDialog


class HMSExtractor:
    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.action = None
        self.dlg = None

    # ---------------------------------------------------------
    def initGui(self):
        icon_path = os.path.join(self.plugin_dir, "icon.png")

        self.action = QAction(QIcon(icon_path), "HMS Extractor", self.iface.mainWindow())
        self.action.setIconText("HMS")
        self.action.setToolTip("HMS Extractor")

        # Hace que QGIS sí muestre texto con el ícono
        self.action.setPriority(QAction.HighPriority)

        self.action.triggered.connect(self.run)

        self.iface.addPluginToMenu("&HMS Extractor", self.action)
        self.iface.addToolBarIcon(self.action)

    # ---------------------------------------------------------
    def unload(self):
        self.iface.removePluginMenu("&HMS Extractor", self.action)
        self.iface.removeToolBarIcon(self.action)

    # ---------------------------------------------------------
    def run(self):
        self.dlg = HMSExtractorDialog(self.iface.mainWindow())
        self.dlg.lineEditOut.setText("HMS_Extracted_Results")

        self.dlg.lineEditFolder.textChanged.connect(self._refresh_basins)
        try:
            self.dlg.btnRun.clicked.disconnect()
        except:
            pass

        self.dlg.btnRun.clicked.connect(self._on_accept)
        self.dlg.show()

    # ---------------------------------------------------------
    def _refresh_basins(self):
        folder = self.dlg.lineEditFolder.text().strip()
        self.dlg.comboBasin.clear()
        if os.path.isdir(folder):
            basins = [f for f in os.listdir(folder) if f.lower().endswith(".basin")]
            basins.sort()
            self.dlg.comboBasin.addItems(basins)

    # ---------------------------------------------------------
    def _on_accept(self):
        vals = self.dlg.get_values()
        folder = vals["folder"]
        basin_name = vals["basin"]
        out_rel = vals["outdir"] or "HMS_Extracted_Results"

        load_elements = vals.get("checkLoadElements", True)
        load_background = vals.get("checkLoadBackground", True)

        if not os.path.isdir(folder):
            QMessageBox.warning(self.iface.mainWindow(), "HMS Extractor",
                                "Selecciona una carpeta válida del proyecto HMS.")
            return

        if not basin_name:
            QMessageBox.warning(self.iface.mainWindow(), "HMS Extractor",
                                "Selecciona un archivo .basin.")
            return

        # Carpetas de salida
        basin_path = os.path.join(folder, basin_name)
        outdir = os.path.join(folder, out_rel)
        out_maps = os.path.join(outdir, "maps")
        os.makedirs(out_maps, exist_ok=True)

        # 1) Leer elementos
        elements = self.parse_basin(basin_path)

        # 2) Leer background
        background_maps = self.parse_background_maps(basin_path, folder) if load_background else []

        # 3) Copiar shapefiles SOLO de background
        for bg in background_maps:
            src = bg.get("src_path")
            if not src or not src.lower().endswith(".shp"):
                continue
            if not os.path.exists(src):
                continue

            dst = os.path.join(out_maps, os.path.basename(src))
            shutil.copy2(src, dst)

            # Extensiones asociadas
            src_base = os.path.splitext(src)[0]
            dst_base = os.path.splitext(dst)[0]
            for ext in [".dbf", ".shx", ".prj", ".cpg"]:
                extra_src = src_base + ext
                if os.path.exists(extra_src):
                    shutil.copy2(extra_src, dst_base + ext)

            bg["copied_path"] = dst

        root = QgsProject.instance().layerTreeRoot()

        # Grupos
        group_hms = root.addGroup("HMS Extracted Results")
        group_bg = root.addGroup("Background Layers")

        # 4) Cargar background en orden inverso
        if load_background:
            for bg in reversed(background_maps):
                if not bg.get("shown"):
                    continue
                shp = bg.get("copied_path")
                if not shp:
                    continue

                name = os.path.splitext(os.path.basename(shp))[0]
                vl = QgsVectorLayer(shp, name, "ogr")
                if vl.isValid():
                    QgsProject.instance().addMapLayer(vl, False)
                    group_bg.addLayer(vl)

        crs = QgsCoordinateReferenceSystem("EPSG:32718")

        # ---------------- ELEMENTOS HMS ----------------
        if load_elements:

            # SUBBASIN CON PARÁMETROS
            etype = "subbasin"
            fields = QgsFields()
            for f in [
                ("name", QVariant.String),
                ("type", QVariant.String),
                ("down", QVariant.String),
                ("area", QVariant.Double),
                ("loss_meth", QVariant.String),
                ("cn", QVariant.Double),
                ("transform", QVariant.String),
                ("tc", QVariant.Double),
                ("stor_coeff", QVariant.Double)
            ]:
                fields.append(QgsField(f[0], f[1]))

            shp_path = os.path.join(outdir, f"{etype}.shp")
            writer = QgsVectorFileWriter(shp_path, "UTF-8", fields, QgsWkbTypes.Point, crs, "ESRI Shapefile")

            for name, e in elements.items():
                if e["type"] != etype:
                    continue
                if "x" in e:
                    feat = QgsFeature()
                    feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(e["x"], e["y"])))
                    feat.setAttributes([
                        name, etype, e.get("downstream", ""),
                        e.get("area"), e.get("loss_meth"),
                        e.get("cn"), e.get("transform"),
                        e.get("tc"), e.get("stor_coeff")
                    ])
                    writer.addFeature(feat)

            del writer

            if os.path.exists(shp_path):
                layer = QgsVectorLayer(shp_path, etype, "ogr")
                QgsProject.instance().addMapLayer(layer, False)
                group_hms.addLayer(layer)
                self.apply_icon_symbol(layer, etype)
                self.enable_labels(layer)

            # OTROS PUNTALES
            for etype in ["junction", "reservoir", "source", "sink"]:
                fields = QgsFields()
                fields.append(QgsField("name", QVariant.String))
                fields.append(QgsField("type", QVariant.String))
                fields.append(QgsField("down", QVariant.String))

                shp_path = os.path.join(outdir, f"{etype}.shp")
                writer = QgsVectorFileWriter(shp_path, "UTF-8", fields, QgsWkbTypes.Point, crs, "ESRI Shapefile")

                for name, e in elements.items():
                    if e["type"] != etype:
                        continue
                    if "x" in e:
                        feat = QgsFeature()
                        feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(e["x"], e["y"])))
                        feat.setAttributes([name, etype, e.get("downstream", "")])
                        writer.addFeature(feat)

                del writer

                if os.path.exists(shp_path):
                    layer = QgsVectorLayer(shp_path, etype, "ogr")
                    QgsProject.instance().addMapLayer(layer, False)
                    group_hms.addLayer(layer)
                    self.apply_icon_symbol(layer, etype)
                    self.enable_labels(layer)

            # ------- REACH -------
            reach_path = os.path.join(outdir, "reach.shp")
            fields = QgsFields()
            fields.append(QgsField("from", QVariant.String))
            fields.append(QgsField("to", QVariant.String))

            writer = QgsVectorFileWriter(reach_path, "UTF-8", fields, QgsWkbTypes.LineString, crs, "ESRI Shapefile")

            for name, e in elements.items():
                dn = e.get("downstream")
                if not dn or dn not in elements:
                    continue
                if elements[dn]["type"] == "reach":
                    feat = QgsFeature()
                    feat.setGeometry(QgsGeometry.fromPolylineXY([
                        QgsPointXY(e["x"], e["y"]),
                        QgsPointXY(elements[dn]["x"], elements[dn]["y"])
                    ]))
                    feat.setAttributes([name, dn])
                    writer.addFeature(feat)

            del writer

            if os.path.exists(reach_path):
                layer = QgsVectorLayer(reach_path, "reach", "ogr")
                QgsProject.instance().addMapLayer(layer, False)
                group_hms.addLayer(layer)
                self.apply_reach_style(layer)
                self.enable_labels_custom(layer, "to")

            # ------- FLOW CONNECTIONS -------
            flow_path = os.path.join(outdir, "flow_connections.shp")
            fields = QgsFields()
            fields.append(QgsField("from", QVariant.String))
            fields.append(QgsField("to", QVariant.String))

            writer = QgsVectorFileWriter(flow_path, "UTF-8", fields, QgsWkbTypes.LineString, crs, "ESRI Shapefile")

            for name, e in elements.items():
                dn = e.get("downstream")
                if dn not in elements:
                    continue
                if elements[dn]["type"] != "reach":
                    feat = QgsFeature()
                    feat.setGeom

