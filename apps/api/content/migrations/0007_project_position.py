"""Le projet prend une position, l'ordre des cartes de la table (D77, issue #288).

Les projets existants la reçoivent à 0, le temps que la migration suivante les numérote dans l'ordre
que la table affichait avant elle : la valeur ne sert qu'à poser la colonne obligatoire sur des
lignes déjà là, le modèle n'en a pas.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0006_cover_to_gallery"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="project",
            options={
                "ordering": ("position", "id"),
                "verbose_name": "projet",
                "verbose_name_plural": "projets",
            },
        ),
        migrations.AddField(
            model_name="project",
            name="position",
            field=models.PositiveSmallIntegerField(blank=True, default=0, verbose_name="position"),
            preserve_default=False,
        ),
    ]
