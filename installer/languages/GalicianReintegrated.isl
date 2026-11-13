; *** Inno Setup version 6.5.0+ Galician (reintegrated, AGAL minimal norm) messages ***
;
; Written for Vitralis from the unofficial Galician translation (Galician.isl, by MdL), in the same
; reintegrated Galician the app's own "Galego reintegrado" uses, and with its informal "tu".
;
; Note: When translating this text, do not add periods (.) to the end of
; messages that didn't have them already, because on those messages Inno
; Setup adds the periods automatically (appending a period would result in
; two periods being displayed).

[LangOptions]
LanguageName=Galego reintegrado
; Windows has no locale for it: Galician users get Galego first, and pick this one in the language dialog
LanguageID=$0456
LanguageCodePage=1252

[Messages]

; *** Application titles
SetupAppTitle=Instalar
SetupWindowTitle=Instalar - %1
UninstallAppTitle=Desinstalar
UninstallAppFullTitle=Desinstalar %1

; *** Misc. common
InformationTitle=Informaçom
ConfirmTitle=Confirmar
ErrorTitle=Erro

; *** SetupLdr messages
SetupLdrStartupMessage=Este programa vai instalar %1. Queres continuar?
LdrCannotCreateTemp=Nom se pudo criar o ficheiro temporário. Instalaçom interrompida
LdrCannotExecTemp=Nom se pudo executar o ficheiro na pasta temporária. Instalaçom interrompida
HelpTextNote=

; *** Startup error messages
LastErrorMessage=%1.%n%nErro %2: %3
SetupFileMissing=O ficheiro %1 nom está na pasta de instalaçom. Resolve o problema ou consegue umha cópia nova do programa.
SetupFileCorrupt=Os ficheiros de instalaçom estám danados. Consegue umha cópia nova do programa.
SetupFileCorruptOrWrongVer=Os ficheiros de instalaçom estám danados ou nom som compatíveis com esta versom do instalador. Resolve o problema ou consegue umha cópia nova do programa.
InvalidParameter=Passou-se um parâmetro nom válido na linha de comandos:%n%n%1
SetupAlreadyRunning=O instalador já está em execuçom.
WindowsVersionNotSupported=Este programa nom é compatível com a versom de Windows do teu computador.
WindowsServicePackRequired=Este programa requer %1 Service Pack %2 ou posterior.
NotOnThisPlatform=Este programa nom funciona em %1.
OnlyOnThisPlatform=Este programa tem que se executar em %1.
OnlyOnTheseArchitectures=Este programa só se pode instalar em versons de Windows desenhadas para as seguintes arquitecturas de processador:%n%n%1
WinVersionTooLowError=Este programa requer %1 versom %2 ou posterior.
WinVersionTooHighError=Este programa nom se pode instalar em %1 versom %2 ou posterior.
AdminPrivilegesRequired=Tens que iniciar sessom como administrador para instalar este programa.
PowerUserPrivilegesRequired=Tens que iniciar sessom como administrador ou como membro do grupo de Utentes Avançados para instalar este programa.
SetupAppRunningError=O instalador detectou que %1 está em execuçom.%n%nFecha-o agora e depois carrega em Aceitar para continuar ou em Cancelar para sair.
UninstallAppRunningError=O desinstalador detectou que %1 está em execuçom.%n%nFecha-o agora e depois carrega em Aceitar para continuar ou em Cancelar para sair.

; *** Startup questions
PrivilegesRequiredOverrideTitle=Seleciona o modo de instalaçom
PrivilegesRequiredOverrideInstruction=Seleciona o modo de instalaçom
PrivilegesRequiredOverrideText1=%1 pode-se instalar para todos os utentes (requer privilégios de administrador) ou só para ti.
PrivilegesRequiredOverrideText2=%1 pode-se instalar só para ti ou para todos os utentes (requer privilégios de administrador).
PrivilegesRequiredOverrideAllUsers=Instalar para &todos os utentes
PrivilegesRequiredOverrideAllUsersRecommended=Instalar para &todos os utentes (recomendado)
PrivilegesRequiredOverrideCurrentUser=Instalar só para &mim
PrivilegesRequiredOverrideCurrentUserRecommended=Instalar só para &mim (recomendado)

; *** Misc. errors
ErrorCreatingDir=O instalador nom pudo criar a pasta "%1"
ErrorTooManyFilesInDir=Nom se pudo criar um ficheiro na pasta "%1" porque contém demasiados ficheiros

; *** Setup common messages
ExitSetupTitle=Sair do instalador
ExitSetupMessage=A instalaçom ainda nom acabou. Se cancelas agora, o programa nom se instalará.%n%nPodes executar o instalador de novo noutro momento para completá-la.%n%nQueres sair do instalador?
AboutSetupMenuItem=&Acerca do instalador...
AboutSetupTitle=Acerca do instalador
AboutSetupMessage=%1 versom %2%n%3%n%nPágina web de %1:%n%4
AboutSetupNote=
TranslatorNote=

; *** Buttons
ButtonBack=< &Atrás
ButtonNext=&Seguinte >
ButtonInstall=&Instalar
ButtonOK=Aceitar
ButtonCancel=Cancelar
ButtonYes=&Sim
ButtonYesToAll=Sim a &tudo
ButtonNo=&Nom
ButtonNoToAll=N&om a tudo
ButtonFinish=&Concluir
ButtonBrowse=&Procurar...
ButtonWizardBrowse=P&rocurar...
ButtonNewFolder=&Criar pasta nova

; *** "Select Language" dialog messages
SelectLanguageTitle=Seleciona a língua do instalador
SelectLanguageLabel=Seleciona a língua que se vai usar durante a instalaçom.

; *** Common wizard text
ClickNext=Carrega em Seguinte para continuar ou em Cancelar para sair do instalador.
BeveledLabel=
BrowseDialogTitle=Procurar pasta
BrowseDialogLabel=Seleciona umha pasta na lista de abaixo e depois carrega em Aceitar.
NewFolderName=Pasta nova

; *** "Welcome" wizard page
WelcomeLabel1=Bem-vindo ao assistente de instalaçom de [name]
WelcomeLabel2=Este programa vai instalar [name/ver] no teu computador.%n%nRecomenda-se fechar as outras aplicaçons antes de continuar.

; *** "Password" wizard page
WizardPassword=Senha
PasswordLabel1=Esta instalaçom está protegida por senha.
PasswordLabel3=Introduz a senha e carrega em Seguinte para continuar. A senha distingue maiúsculas e minúsculas.
PasswordEditLabel=&Senha:
IncorrectPassword=A senha que introduziste nom é correcta. Tenta-o de novo.

; *** "License Agreement" wizard page
WizardLicense=Acordo de licença
LicenseLabel=É importante que leias a seguinte informaçom antes de continuar.
LicenseLabel3=Lê o seguinte acordo de licença. Tens que aceitar os termos deste acordo antes de continuar com a instalaçom.
LicenseAccepted=A&ceito o acordo
LicenseNotAccepted=N&om aceito o acordo

; *** "Information" wizard pages
WizardInfoBefore=Informaçom
InfoBeforeLabel=É importante que leias a seguinte informaçom antes de continuar.
InfoBeforeClickLabel=Quando estiveres pronto para continuar com a instalaçom, carrega em Seguinte.
WizardInfoAfter=Informaçom
InfoAfterLabel=É importante que leias a seguinte informaçom antes de continuar.
InfoAfterClickLabel=Quando estiveres pronto para continuar com a instalaçom, carrega em Seguinte.

; *** "User Information" wizard page
WizardUserInfo=Informaçom do utente
UserInfoDesc=Introduz a tua informaçom.
UserInfoName=&Nome de utente:
UserInfoOrg=&Organizaçom:
UserInfoSerial=Número de &série:
UserInfoNameRequired=Tens que introduzir um nome.

; *** "Select Destination Location" wizard page
WizardSelectDir=Seleciona a pasta de destino
SelectDirDesc=Onde queres instalar [name]?
SelectDirLabel3=O instalador vai instalar [name] na seguinte pasta.
SelectDirBrowseLabel=Para continuar, carrega em Seguinte. Se queres selecionar outra pasta, carrega em Procurar.
DiskSpaceGBLabel=Requerem-se polo menos [gb] GB de espaço livre no disco.
DiskSpaceMBLabel=Requerem-se polo menos [mb] MB de espaço livre no disco.
CannotInstallToNetworkDrive=O instalador nom pode instalar numha unidade de rede.
CannotInstallToUNCPath=O instalador nom pode instalar num caminho UNC.
InvalidPath=Tens que introduzir um caminho completo com a letra da unidade; por exemplo:%n%nC:\APP%n%nou um caminho UNC com o formato:%n%n\\servidor\recurso
InvalidDrive=A unidade ou o caminho UNC que selecionaste nom existe ou nom está acessível. Seleciona outro.
DiskSpaceWarningTitle=Espaço insuficiente no disco
DiskSpaceWarning=O instalador requer polo menos %1 KB de espaço livre, mas a unidade selecionada só tem %2 KB disponíveis.%n%nQueres continuar mesmo assim?
DirNameTooLong=O nome da pasta ou o caminho som demasiado longos.
InvalidDirName=O nome da pasta nom é válido.
BadDirName32=Os nomes das pastas nom podem incluir nengum dos seguintes caracteres:%n%n%1
DirExistsTitle=A pasta já existe
DirExists=A pasta:%n%n%1%n%njá existe. Queres instalar nessa pasta mesmo assim?
DirDoesntExistTitle=A pasta nom existe
DirDoesntExist=A pasta:%n%n%1%n%nnom existe. Queres criá-la?

; *** "Select Components" wizard page
WizardSelectComponents=Seleciona os componentes
SelectComponentsDesc=Que componentes queres instalar?
SelectComponentsLabel2=Seleciona os componentes que queres instalar e desmarca os que nom queiras instalar. Carrega em Seguinte quando estiveres pronto para continuar.
FullInstallation=Instalaçom completa
; if possible don't translate 'Compact' as 'Minimal' (I mean 'Minimal' in your language)
CompactInstallation=Instalaçom compacta
CustomInstallation=Instalaçom personalizada
NoUninstallWarningTitle=Componentes encontrados
NoUninstallWarning=O instalador detectou que os seguintes componentes já estám instalados no teu computador:%n%n%1%n%nDesmarcar estes componentes nom os desinstala.%n%nQueres continuar mesmo assim?
ComponentSize1=%1 KB
ComponentSize2=%1 MB
ComponentsDiskSpaceGBLabel=A seleçom actual requer polo menos [gb] GB de espaço livre no disco.
ComponentsDiskSpaceMBLabel=A seleçom actual requer polo menos [mb] MB de espaço livre no disco.

; *** "Select Additional Tasks" wizard page
WizardSelectTasks=Seleciona as tarefas adicionais
SelectTasksDesc=Que tarefas adicionais queres fazer?
SelectTasksLabel2=Seleciona as tarefas adicionais que queres fazer durante a instalaçom de [name] e carrega em Seguinte.

; *** "Select Start Menu Folder" wizard page
WizardSelectProgramGroup=Seleciona a pasta do menu Iniciar
SelectStartMenuFolderDesc=Onde queres que o instalador ponha os atalhos do programa?
SelectStartMenuFolderLabel3=O instalador vai criar os atalhos do programa na seguinte pasta do menu Iniciar.
SelectStartMenuFolderBrowseLabel=Para continuar, carrega em Seguinte. Se queres selecionar outra pasta, carrega em Procurar.
MustEnterGroupName=Tens que dar um nome à pasta.
GroupNameTooLong=O nome da pasta ou o caminho som demasiado longos.
InvalidGroupName=O nome da pasta nom é válido.
BadGroupName=O nome da pasta nom pode incluir nengum dos seguintes caracteres:%n%n%1
NoProgramGroupCheck2=&Nom criar umha pasta no menu Iniciar

; *** "Ready to Install" wizard page
WizardReady=Pronto para instalar
ReadyLabel1=O instalador está pronto para começar a instalaçom de [name] no teu computador.
ReadyLabel2a=Carrega em Instalar para continuar, ou em Atrás se queres rever ou mudar a configuraçom.
ReadyLabel2b=Carrega em Instalar para continuar com a instalaçom.
ReadyMemoUserInfo=Informaçom do utente:
ReadyMemoDir=Pasta de destino:
ReadyMemoType=Tipo de instalaçom:
ReadyMemoComponents=Componentes selecionados:
ReadyMemoGroup=Pasta do menu Iniciar:
ReadyMemoTasks=Tarefas adicionais:

; *** TDownloadWizardPage wizard page and DownloadTemporaryFile
DownloadingLabel2=Descarregando ficheiros...
ButtonStopDownload=&Parar a descarga
StopDownload=Tens a certeza de que queres parar a descarga?
ErrorDownloadAborted=Descarga cancelada
ErrorDownloadFailed=A descarga falhou: %1 %2
ErrorDownloadSizeFailed=Nom se pudo obter o tamanho: %1 %2
ErrorProgress=Progresso nom válido: %1 de %2
ErrorFileSize=Tamanho do ficheiro nom válido: esperava-se %1, encontrou-se %2

; *** TExtractionWizardPage wizard page and ExtractArchive
ExtractingLabel=Extraindo ficheiros...
ButtonStopExtraction=&Parar a extraçom
StopExtraction=Tens a certeza de que queres parar a extraçom?
ErrorExtractionAborted=Extraçom cancelada
ErrorExtractionFailed=A extraçom falhou: %1

; *** Archive extraction failure details
ArchiveIncorrectPassword=A senha nom é correcta
ArchiveIsCorrupted=O arquivo está danado
ArchiveUnsupportedFormat=O formato do arquivo nom é compatível

; *** "Preparing to Install" wizard page
WizardPreparing=Preparando a instalaçom
PreparingDesc=O instalador está a preparar a instalaçom de [name] no teu computador.
PreviousInstallNotCompleted=A instalaçom ou desinstalaçom de um programa anterior nom se completou. Tens que reiniciar o computador para completá-la.%n%nDepois de reiniciar, executa o instalador de novo para completar a instalaçom de [name].
CannotContinue=O instalador nom pode continuar. Carrega em Cancelar para sair.
ApplicationsFound=As seguintes aplicaçons estám a usar ficheiros que o instalador tem que atualizar. Recomenda-se deixar que o instalador feche estas aplicaçons automaticamente.
ApplicationsFound2=As seguintes aplicaçons estám a usar ficheiros que o instalador tem que atualizar. Recomenda-se deixar que o instalador feche estas aplicaçons automaticamente. Quando a instalaçom acabar, o instalador tentará reiniciá-las.
CloseApplications=&Fechar as aplicaçons automaticamente
DontCloseApplications=&Nom fechar as aplicaçons
ErrorCloseApplications=O instalador nom pudo fechar automaticamente todas as aplicaçons. Recomenda-se que, antes de continuar, feches todas as aplicaçons que usam ficheiros que o instalador tem que atualizar.
PrepareToInstallNeedsRestart=O instalador tem que reiniciar o computador. Depois de reiniciar, executa o instalador de novo para completar a instalaçom de [name].%n%nQueres reiniciar o computador agora?

; *** "Installing" wizard page
WizardInstalling=Instalando
InstallingLabel=Aguarda enquanto se instala [name] no teu computador.

; *** "Setup Completed" wizard page
FinishedHeadingLabel=Completando a instalaçom de [name]
FinishedLabelNoIcons=O instalador completou a instalaçom de [name] no teu computador.
FinishedLabel=O instalador completou a instalaçom de [name] no teu computador. Podes abrir a aplicaçom com os atalhos criados.
ClickFinish=Carrega em Concluir para sair do instalador.
FinishedRestartLabel=Para completar a instalaçom de [name], o teu computador tem que se reiniciar. Queres reiniciá-lo agora?
FinishedRestartMessage=Para completar a instalaçom de [name], o teu computador tem que se reiniciar.%n%nQueres reiniciá-lo agora?
ShowReadmeCheck=Sim, quero ver o ficheiro lê-me (README)
YesRadio=&Sim, quero reiniciar o computador agora
NoRadio=&Nom, reiniciarei o computador mais tarde
; used for example as 'Run MyProg.exe'
RunEntryExec=Executar %1
; used for example as 'View Readme.txt'
RunEntryShellExec=Ver %1

; *** "Setup Needs the Next Disk" stuff
ChangeDiskTitle=O instalador precisa do seguinte disco
SelectDiskLabel2=Insere o disco %1 e carrega em Aceitar.%n%nSe os ficheiros estám numha pasta diferente da que se mostra abaixo, introduz o caminho correcto ou carrega em Procurar.
PathLabel=&Caminho:
FileNotInDir2=Nom se encontrou o ficheiro "%1" em "%2". Insere o disco correcto ou seleciona outra pasta.
SelectDirectoryLabel=Indica a localizaçom do seguinte disco.

; *** Installation phase messages
SetupAborted=A instalaçom nom se completou.%n%nResolve o problema e executa o instalador de novo.
AbortRetryIgnoreSelectAction=Seleciona umha açom
AbortRetryIgnoreRetry=&Tentar de novo
AbortRetryIgnoreIgnore=&Ignorar o erro e continuar
AbortRetryIgnoreCancel=Cancelar a instalaçom
RetryCancelSelectAction=Seleciona umha açom
RetryCancelRetry=&Tentar de novo
RetryCancelCancel=Cancelar

; *** Installation status messages
StatusClosingApplications=Fechando aplicaçons...
StatusCreateDirs=Criando pastas...
StatusExtractFiles=Extraindo ficheiros...
StatusDownloadFiles=Descarregando ficheiros...
StatusCreateIcons=Criando atalhos...
StatusCreateIniEntries=Criando entradas INI...
StatusCreateRegistryEntries=Criando entradas do registo...
StatusRegisterFiles=Registando ficheiros...
StatusSavingUninstall=Guardando a informaçom para desinstalar...
StatusRunProgram=Acabando a instalaçom...
StatusRestartingApplications=Reiniciando aplicaçons...
StatusRollback=Desfazendo as mudanças...

; *** Misc. errors
ErrorInternal2=Erro interno: %1
ErrorFunctionFailedNoCode=%1 falhou
ErrorFunctionFailed=%1 falhou; código %2
ErrorFunctionFailedWithMessage=%1 falhou; código %2.%n%3
ErrorExecutingProgram=Nom se pudo executar o ficheiro:%n%1

; *** Registry errors
ErrorRegOpenKey=Erro ao abrir a chave do registo:%n%1\%2
ErrorRegCreateKey=Erro ao criar a chave do registo:%n%1\%2
ErrorRegWriteKey=Erro ao escrever a chave do registo:%n%1\%2

; *** INI errors
ErrorIniEntry=Erro ao criar a entrada INI no ficheiro "%1".

; *** File copying errors
FileAbortRetryIgnoreSkipNotRecommended=&Saltar este ficheiro (nom recomendado)
FileAbortRetryIgnoreIgnoreNotRecommended=&Ignorar o erro e continuar (nom recomendado)
SourceIsCorrupted=O ficheiro de origem está danado
SourceDoesntExist=O ficheiro de origem "%1" nom existe
SourceVerificationFailed=A verificaçom do ficheiro de origem falhou: %1
VerificationSignatureDoesntExist=O ficheiro de assinatura "%1" nom existe
VerificationSignatureInvalid=O ficheiro de assinatura "%1" nom é válido
VerificationKeyNotFound=O ficheiro de assinatura "%1" usa umha chave desconhecida
VerificationFileNameIncorrect=O nome do ficheiro nom é correcto
VerificationFileTagIncorrect=A etiqueta do ficheiro nom é correcta
VerificationFileSizeIncorrect=O tamanho do ficheiro nom é correcto
VerificationFileHashIncorrect=O hash do ficheiro nom é correcto
ExistingFileReadOnly2=O ficheiro existente nom se pode substituir porque está marcado como só de leitura.
ExistingFileReadOnlyRetry=&Tirar o atributo só de leitura e tentar de novo
ExistingFileReadOnlyKeepExisting=&Manter o ficheiro existente
ErrorReadingExistingDest=Houvo um erro ao tentar ler o ficheiro existente:
FileExistsSelectAction=Seleciona umha açom
FileExists2=O ficheiro já existe.
FileExistsOverwriteExisting=&Substituir o ficheiro existente
FileExistsKeepExisting=&Manter o ficheiro existente
FileExistsOverwriteOrKeepAll=&Fazer o mesmo nos próximos conflitos
ExistingFileNewerSelectAction=Seleciona umha açom
ExistingFileNewer2=O ficheiro existente é mais recente que o que se está a tentar instalar.
ExistingFileNewerOverwriteExisting=&Substituir o ficheiro existente
ExistingFileNewerKeepExisting=&Manter o ficheiro existente (recomendado)
ExistingFileNewerOverwriteOrKeepAll=&Fazer o mesmo nos próximos conflitos
ErrorChangingAttr=Houvo um erro ao tentar mudar os atributos do ficheiro existente:
ErrorCreatingTemp=Houvo um erro ao tentar criar um ficheiro na pasta de destino:
ErrorReadingSource=Houvo um erro ao tentar ler o ficheiro de origem:
ErrorCopying=Houvo um erro ao tentar copiar um ficheiro:
ErrorDownloading=Houvo um erro ao tentar descarregar um ficheiro:
ErrorExtracting=Houvo um erro ao tentar extrair um arquivo:
ErrorReplacingExistingFile=Houvo um erro ao tentar substituir o ficheiro existente:
ErrorRestartReplace=Houvo um erro ao tentar substituir o ficheiro ao reiniciar o computador:
ErrorRenamingTemp=Houvo um erro ao tentar mudar o nome de um ficheiro na pasta de destino:
ErrorRegisterServer=Nom se pudo registar o DLL/OCX: %1
ErrorRegSvr32Failed=RegSvr32 falhou com o código de saída %1
ErrorRegisterTypeLib=Nom se pudo registar a biblioteca de tipos: %1

; *** Uninstall display name markings
UninstallDisplayNameMark=%1 (%2)
UninstallDisplayNameMarks=%1 (%2, %3)
UninstallDisplayNameMark32Bit=32 bits
UninstallDisplayNameMark64Bit=64 bits
UninstallDisplayNameMarkAllUsers=Todos os utentes
UninstallDisplayNameMarkCurrentUser=Utente actual

; *** Post-installation errors
ErrorOpeningReadme=Houvo um erro ao tentar abrir o ficheiro lê-me (README).
ErrorRestartingComputer=O instalador nom pudo reiniciar o computador. Reinicia-o à mao.

; *** Uninstaller messages
UninstallNotFound=O ficheiro "%1" nom existe. Nom se pode desinstalar.
UninstallOpenError=Nom se pudo abrir o ficheiro "%1". Nom se pode desinstalar.
UninstallUnsupportedVer=O ficheiro de registo da desinstalaçom "%1" está num formato que esta versom do desinstalador nom reconhece. Nom se pode desinstalar.
UninstallUnknownEntry=Encontrou-se umha entrada desconhecida (%1) no registo da desinstalaçom.
ConfirmUninstall=Tens a certeza de que queres eliminar por completo %1 e todos os seus componentes?
UninstallOnlyOnWin64=Este programa só se pode desinstalar em Windows de 64 bits.
OnlyAdminCanUninstall=Este programa só o pode desinstalar um utente com privilégios de administrador.
UninstallStatusLabel=Aguarda enquanto se elimina %1 do teu computador.
UninstalledAll=%1 eliminou-se do teu computador com sucesso.
UninstalledMost=A desinstalaçom de %1 completou-se.%n%nAlguns elementos nom se puderom eliminar; podes eliminá-los à mao.
UninstalledAndNeedsRestart=Para completar a desinstalaçom de %1, o teu computador tem que se reiniciar.%n%nQueres reiniciá-lo agora?
UninstallDataCorrupted=O ficheiro "%1" está danado. Nom se pode desinstalar.

; *** Uninstallation phase messages
ConfirmDeleteSharedFileTitle=Eliminar o ficheiro partilhado?
ConfirmDeleteSharedFile2=O sistema indica que o seguinte ficheiro partilhado já nom o usa nengum programa. Queres eliminar este ficheiro partilhado?%n%nSe o eliminas e algum programa ainda o usa, esse programa pode deixar de funcionar bem. Se nom tens a certeza, escolhe Nom. Deixar o ficheiro no sistema nom fai nengum dano.
SharedFileNameLabel=Ficheiro:
SharedFileLocationLabel=Localizaçom:
WizardUninstalling=Estado da desinstalaçom
StatusUninstalling=Desinstalando %1...

; *** Shutdown block reasons
ShutdownBlockReasonInstallingApp=Instalando %1.
ShutdownBlockReasonUninstallingApp=Desinstalando %1.

; The custom messages below aren't used by Setup itself, but if you make
; use of them in your scripts, you'll want to translate them.

[CustomMessages]

NameAndVersion=%1 versom %2
AdditionalIcons=Atalhos adicionais:
CreateDesktopIcon=Criar um atalho na área de &trabalho
CreateQuickLaunchIcon=Criar um atalho no &início rápido
ProgramOnTheWeb=%1 na web
UninstallProgram=Desinstalar %1
LaunchProgram=Abrir %1
AssocFileExtension=&Associar %1 à extensom de ficheiro %2
AssocingFileExtension=Associando %1 à extensom de ficheiro %2...
AutoStartProgramGroupDescription=Início:
AutoStartProgram=Iniciar %1 automaticamente
AddonHostProgramNotFound=Nom se encontrou %1 na pasta selecionada.%n%nQueres continuar mesmo assim?
