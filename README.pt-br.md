## [Read in English (Leia em Inglês)](README.md)

# Twitch SO Bot (Bot de Shoutout)

Um bot para Twitch que exibe clipes, vídeos ou destaques aleatórios de canais específicos sem depender de serviços de terceiros. O bot se integra ao OBS para mostrar automaticamente o conteúdo quando usuários autorizados executam o comando `!so` no chat da sua Twitch.

## Funcionalidades

- Exibe clipes, vídeos ou destaques aleatórios de qualquer canal da Twitch
- Integração direta com OBS via WebSocket
- Tipos de conteúdo personalizáveis (clipes, vídeos, destaques)
- Bloqueio de comandos baseado em horário
- Sistema de autorização de usuários
- Registro de uso de comandos
- Interface de configuração baseada na web

## Requisitos

- [OBS Studio](https://obsproject.com/) com o plugin WebSocket ativado
- Conta na Twitch
- Aplicativo de Desenvolvedor da Twitch

## Instalação

1. Baixe a versão mais recente do `so_bot.exe` em [GitHub Releases](https://github.com/pladombrowski/so_bot/releases)
2. Execute o arquivo executável no seu computador
3. O aplicativo abrirá uma janela do navegador para autenticação na Twitch
4. Após a autenticação, acesse a página de configuração em http://localhost:5000/config

## Configuração

### Aplicativo de Desenvolvedor da Twitch

1. Acesse o [Console de Desenvolvedor da Twitch](https://dev.twitch.tv/)
2. Registre um novo aplicativo
3. Escolha um nome para o seu aplicativo
4. No campo "URLs de Redirecionamento OAuth", insira:
   ```
   http://localhost:5000/auth/callback
   ```
5. Defina a categoria como "Chat Bot"
6. Complete o CAPTCHA e salve
7. Copie o "ID do Cliente" e o "Segredo do Cliente" para configuração

### Configuração do WebSocket do OBS

1. No OBS, vá para Ferramentas > Configurações do Servidor WebSocket
2. Marque "Ativar Servidor WebSocket"
3. Clique em "Mostrar Informações de Conexão" para ver sua senha
4. Anote o servidor, porta e senha para configuração

### Configuração do Bot

1. Acesse a página de configuração em http://localhost:5000/config
2. Insira seu ID do Cliente e Segredo do Cliente da Twitch
3. Insira os detalhes de conexão do WebSocket do OBS
4. Defina a duração máxima do vídeo (em segundos)
5. Adicione usuários autorizados que podem executar o comando `!so` (separados por vírgula)
6. Configure o período de tempo em que os comandos devem ser bloqueados (se desejado)
7. Selecione os tipos de conteúdo que deseja exibir (clipes, vídeos, destaques)
8. Clique em "Salvar Configurações" para aplicar sua configuração e iniciar o bot

## Uso

Uma vez configurado, usuários autorizados podem usar o seguinte comando no chat da sua Twitch:

```
!so nome_do_canal
```

Isso irá buscar conteúdo do canal especificado e exibir um clipe, vídeo ou destaque aleatório na sua cena do OBS.

## Solução de Problemas

- Certifique-se de que o OBS está em execução com o servidor WebSocket ativado
- Verifique se as credenciais do seu Aplicativo de Desenvolvedor da Twitch estão corretas
- Verifique se você tem uma cena chamada "Twitch Auto" na sua configuração do OBS
- Certifique-se de que o bot tem a autorização adequada verificando o arquivo tokens.yaml

## Dependências

- requests
- Flask
- flask-cors
- PyYAML
- twitchio
- obs-websocket-py
- asqlite

## Licença

Este projeto está disponível como código aberto sob os termos da Licença MIT.