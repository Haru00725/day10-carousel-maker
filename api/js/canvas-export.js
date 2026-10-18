/**
 * Aesthetic Scrapbook Carousel Maker — Canvas Export & ZIP Bundler
 */

const CanvasExporter = {
  /**
   * Exports a single slide canvas as PNG data URL or Blob.
   */
  async exportSlideCanvas(fabricCanvas, multiplier = 1) {
    return new Promise((resolve) => {
      // Temporarily deselect any active object to remove bounding boxes
      fabricCanvas.discardActiveGroup ? fabricCanvas.discardActiveGroup() : fabricCanvas.discardActiveObject();
      fabricCanvas.renderAll();

      const dataUrl = fabricCanvas.toDataURL({
        format: 'png',
        quality: 1,
        multiplier: multiplier
      });
      resolve(dataUrl);
    });
  },

  /**
   * Downloads a single slide as PNG.
   */
  downloadDataUrl(dataUrl, filename = 'scrapbook_slide.png') {
    const a = document.createElement('a');
    a.href = dataUrl;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  },

  /**
   * Bundles all rendered slide images (base64 data URLs) into a high-res ZIP.
   */
  async exportAllAsZip(slidesDataUrls, zipFilename = 'scrapbook_carousel.zip') {
    if (!window.JSZip) {
      alert('JSZip library is still loading, please wait a moment.');
      return;
    }

    const zip = new JSZip();
    const folder = zip.folder('scrapbook_carousel');

    slidesDataUrls.forEach((dataUrl, idx) => {
      // Remove base64 data prefix
      const base64Data = dataUrl.split(',')[1];
      const slideNum = String(idx + 1).padStart(2, '0');
      folder.file(`slide_${slideNum}.png`, base64Data, { base64: true });
    });

    const content = await zip.generateAsync({ type: 'blob' });
    if (window.saveAs) {
      saveAs(content, zipFilename);
    } else {
      const url = URL.createObjectURL(content);
      const a = document.createElement('a');
      a.href = url;
      a.download = zipFilename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    }
  },

  /**
   * Saves the current design specification as a JSON file.
   */
  saveDesignJson(spec, filename = 'scrapbook_design.json') {
    const jsonStr = JSON.stringify(spec, null, 2);
    const blob = new Blob([jsonStr], { type: 'application/json' });
    if (window.saveAs) {
      saveAs(blob, filename);
    } else {
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    }
  }
};

window.CanvasExporter = CanvasExporter;
