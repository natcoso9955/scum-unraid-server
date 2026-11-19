# Unraid template for an existing template repo

Upload `templates/scum-server.xml` to the `templates/` folder of your existing repo after running `configure-release.ps1`. Do not replace your existing repo `ca_profile.xml`. The template must point at an image that exists on Docker Hub. Unraid Docker templates do not build images from Dockerfiles; they pull the published image. Review and test this XML before Community Apps submission.
