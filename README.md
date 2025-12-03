# Joystick-Gremlin-Thrustmaster-Sol-R2-Leds-plugin
# Plugin per controllare i led del sol-r2 


# Installazione:
# Testato su windows 10
# devi aver installato python 
# per prima cosa devi sostituire i driver degli hotas tramite Zadig, per evitare essi vengano ripristinati dal sistema devi disattivare i servizi Thrustmaster FAST service e Thrustmaster Hotas Service
# in zadig in options spunta List all devices nella lista seleziona VENDOR (Interface 1),"ATTENZIONE NON CAMBIARE I DRIVER DI SOL-R/L FLIGHTSTICK INTERFACE 0".
# attualmente hai il driver tmhbulk, devi installare il driver Libusbk, ripeti per l'altro hotas
# una volta sostituiti i driver scollega e ricollega le 2 periferiche, in zadig adesso dovresti vedere nelle interfacce VENDOR i driver libusbK.
# apri il percorso di installazione di gremlin "di solito C:\Program Files (x86)\H2ik\Joystick Gremlin\" e nella cartella action_plugins estrai l'archivio leds, nella cartella C:\Program Files (x86)\H2ik\Joystick 
# Gremlin\Plugins estrai l'archivio server.
# 
