ESTUDIO RODRIGUEZ - WEB V4.3 - AGENDA FISCAL AUTOMATICA

Qué cambia respecto de V4.2
- V4.2 queda intacta como respaldo.
- V4.3 carga agenda_fiscal.json al abrir la web.
- scripts/update_agenda.py consulta únicamente páginas oficiales ARCA/ARBA.
- Si una fuente falla o cambia su HTML, conserva el último dato válido de esa categoría.
- Si el JSON no está disponible, index.html usa la agenda V4.2 embebida como respaldo.
- La web informa si está usando actualización automática o modo respaldo.

Ejecución manual en Windows
1) Instalar dependencias una vez: pip install -r requirements.txt
2) Ejecutar scripts\actualizar_agenda.bat

Automatización al publicar
Se incluye .github/workflows/actualizar-agenda.yml para GitHub Actions.
Corre diariamente y también puede ejecutarse manualmente.
Para que actualice una web pública, el repositorio/hosting debe publicar este directorio.

IMPORTANTE
La extracción depende de la estructura pública de los sitios oficiales. Si ARCA o ARBA cambian el HTML, el sistema evita borrar el último dato válido, pero conviene revisar periódicamente el log de actualización.
Las fechas deben considerarse informativas y contrastarse con la fuente oficial ante prórrogas o cambios normativos.
