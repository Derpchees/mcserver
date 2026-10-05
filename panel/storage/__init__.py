#
# MCServer by Derpchees - almacenamiento
# https://github.com/Derpchees/mcserver
#
# Donde viven los servidores y los respaldos, y el espacio reservado para
# ellos. Un espacio reservado tiene tamano fijo: MCServer no puede pasarse
# de el y nada mas en el disco puede usarlo. Puede ser:
#   - una particion nueva en espacio libre de un disco (o en un disco vacio)
#   - una particion existente sin montar
#   - un volumen LVM (si el disco usa LVM y tiene espacio sin asignar)
#   - un archivo de disco que se aparta completo y se monta como un disco
# Nunca se formatea, achica ni borra una particion que ya existe.
#
#   system.py    lectura del sistema: discos, montajes, LVM, huecos libres
#   disks.py     a que disco fisico pertenece una ruta o dispositivo
#   status.py    estado de las ubicaciones de servidores y respaldos
#   options.py   destinos posibles
#   jobs.py      tareas en segundo plano
#   spaces.py    crear y montar espacios (particiones, LVM, archivos)
#   relocate.py  mover datos, agrandar, pausar respaldos
#   rebuild.py   rehacer un disco con poco contenido sin perderlo
#
# Lo usan el panel (estado y tareas) y el agente (deteccion de discos).
#
