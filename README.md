
# Twitch So Bot
Bot para rodar um destaque de usuários na twitch sem depender de sites terceiros!


## Utilização

Para utilizar o so_bot você deve entrar em: https://dev.twitch.tv/

Já no painel dev da twitch, você deve registrar seu aplicativo.

Escolha um nome para o seu aplicativo.

No campo "URLs de redirecionamento OAuth" você deve colocar:

```
  http://localhost:5000/auth/callback
```

No campo "Categoria" você deve escolher "Chat Bot"

Verifique o captcha e salve!

Já na tela do aplicativo novo, copie o "ID do Cliente"

Se a tela exibir um segredo, copie também, se não exibir, clique em "Novo segredo" e copie ele.

Após a criar o aplicativo e anotar o ID e Segredo do cliente entre na página de releases do git: https://github.com/pladombrowski/so_bot/releases

Faça download do so_bot.exe mais atual.

Execute ele no seu pc para iniciar a configuração.

Ele vai acessar a sua twitch para gerar o oath token, basta autorizar ele.

Após autorizado acesse: http://localhost:5000/config

Utilize as informações copiadas no painel dev da twitch para configurar o bot.

Preencha as informaçòes do websocket do OBS também.

Para obter elas no OBS entre em: Ferramentas > Configurações do servidor websocket > Mostrar Informações de Conexão.
    
```
OBS: A opção Ativar servidor WebSocket deve estar marcada, após marcar ela clique em aplicar para iniciar o servidor WebSocket
```

Por ultimo, na area de "Usuários Autorizados" você deve adicionar os logins dos usuários que você quer permitir que rodem os comandos de !so separados por vírgula, por exemplo:

```
usuario1,usuario2,usuario3
```

Com todas informações preenchidas clique em "SALVAR CONFIGURAÇÕES" para salvar elas e iniciar o SO_BOT.

Após isto qualquer comando !so canal_da_twitch vai gerar uma busca por videos no canal informado e mostrar no seu OBS um video aleatório encontrado.