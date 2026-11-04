"""Owner-only installation page and public-source extension package."""
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from flask import abort, render_template, request, send_file


RUNTIME_FILES = ('manifest.json', 'background.mjs', 'controller.mjs', 'reader.mjs', 'page-readers.mjs', 'evidence.mjs')


def register(app, require_owner, context):
    def authorize():
        require_owner()
        if request.host != 'stuff.armenante.com':
            abort(404)

    @app.get('/ebay/browser/setup')
    def ebay_browser_setup():
        authorize()
        return render_template('ebay_browser_setup.html', **context())

    @app.get('/ebay/browser/download')
    def ebay_browser_download():
        authorize()
        folder = Path(__file__).with_name('browser-extension')
        archive = BytesIO()
        with ZipFile(archive, 'w', compression=ZIP_DEFLATED) as package:
            for name in RUNTIME_FILES:
                package.writestr('browser-extension/' + name, (folder / name).read_bytes())
        archive.seek(0)
        response = send_file(archive, mimetype='application/zip', as_attachment=True,
                             download_name='stuffapp-ebay-browser.zip', max_age=0)
        response.headers['Cache-Control'] = 'no-store'
        return response
