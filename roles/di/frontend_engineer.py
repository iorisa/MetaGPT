async def _think(self) -> bool:
    # ... existing code ...
    
    if self.is_first_dev_request:
        logger.info(f"First dev request, handle template")
        try:
            # 修改这里的解包逻辑
            result = await self.handle_template(send_msg.content)
            if isinstance(result, tuple):
                template_result, user_info = result
            else:
                template_result, user_info = result, None
                
            logger.info(f"Template search result: {template_result}")

            content = "This is First Dev Request, I have already handled the template, now I will start to develop the project. \n\nThe following is the template information and user information.\n\n"
            content += f"{content}\n\n{template_result}\n\nUser info: {user_info}"
            # Update memory
            self.rc.memory.add(UserMessage(content=content))
            logger.info(f"First dev request, memory updated")
            self.is_first_dev_request = False  # Update flag
        except Exception as e:
            logger.error(f"Error handling template: {str(e)}")
            return False

    # ... existing code ... 