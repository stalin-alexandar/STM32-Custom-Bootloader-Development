/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file           : main.c
  * @brief          : Main program body
  ******************************************************************************
  * @attention
  *
  * Copyright (c) 2026 STMicroelectronics.
  * All rights reserved.
  *
  * This software is licensed under terms that can be found in the LICENSE file
  * in the root directory of this software component.
  * If no LICENSE file comes with this software, it is provided AS-IS.
  *
  ******************************************************************************
  */
#include <stdio.h>
#include <string.h>
#include <stdarg.h>
/* USER CODE END Header */
/* Includes ------------------------------------------------------------------*/
#include "main.h"

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */
#define PRINTF
#define OB_HAL 1
#define SECTOR2_FLASH_STORAGE 0x08008000UL

/* USER CODE END Includes */

/* Private typedef -----------------------------------------------------------*/
/* USER CODE BEGIN PTD */

/* USER CODE END PTD */

/* Private define ------------------------------------------------------------*/
/* USER CODE BEGIN PD */

/* USER CODE END PD */

/* Private macro -------------------------------------------------------------*/
/* USER CODE BEGIN PM */

/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/
CRC_HandleTypeDef hcrc;

UART_HandleTypeDef huart2;
UART_HandleTypeDef huart3;

/* USER CODE BEGIN PV */
#define D_UART &huart3
#define C_UART &huart2

/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
void SystemClock_Config(void);
static void MX_GPIO_Init(void);
static void MX_CRC_Init(void);
static void MX_USART3_UART_Init(void);
static void MX_USART2_UART_Init(void);
/* USER CODE BEGIN PFP */
static void printmsg(char *formate,...);
static void bootloader_uart_read_data();
static void bootloader_uart_write_data(uint8_t* pSTACK, uint8_t len);
static void bootloader_jump_to_user_app();

void bl_get_version(uint8_t* pSTACK);
void bl_get_help(uint8_t* pSTACK);
void bl_get_CID(uint8_t* pSTACK);
void bl_get_read_protection_level(uint8_t* pSTACK);
void bl_go_to_address(uint8_t* pSTACK);
void bl_erase_flash(uint8_t* pSTACK);
void bl_memory_write(uint8_t* pSTACK);
void bl_memory_read(uint8_t* pSTACK);
void bl_en_read_write_protection(uint8_t* pSTACK);
void bl_get_read_sector_protection_status(uint8_t* pSTACK);
void read_otp_content(uint8_t* pSTACK);
void bl_diable_read_write_protection(uint8_t* pSTACK);

static void bootloader_send_ack(uint8_t cmd_code, uint8_t follow_len);
static void bootloader_send_nack(void);
static uint8_t bootloader_verify_crc(uint8_t* pSTACK, uint8_t len, uint32_t host_crc);
static uint8_t get_booloader_ver();
static uint16_t get_mcu_cid();
static uint8_t get_rdp_level();
static uint8_t validate_addr(uint32_t addr);

static uint8_t execute_erase_task(uint8_t sector_number, uint8_t number_of_sector);
static uint8_t execute_write_task(uint32_t base_mem_addr, uint8_t *pBuffer, uint32_t payload_len);

static uint8_t sector_status(uint8_t sector_view, uint8_t protection_mode, uint8_t disable);

/* USER CODE END PFP */

/* Private user code ---------------------------------------------------------*/
/* USER CODE BEGIN 0 */
uint8_t BL_FULL_STACK[250];

uint8_t HELP_CODE[] = {
		BL_GET_VER,
		BL_GET_HELP,
		BL_GET_CID,
		BL_GET_RPD_STATUS,
		BL_GO_TO_ADDR,
		BL_FLASH_ERASE,
		BL_MEM_WRITE,
		BL_MEM_READ,
		BL_EN_R_W_PROTECT,
		BL_READ_SECTOR_STATUS,
		BL_OTP_READ,
		BL_DIS_R_RW_PROTECT

};
/* USER CODE END 0 */

/**
  * @brief  The application entry point.
  * @retval int
  */
int main(void)
{

  /* USER CODE BEGIN 1 */

  /* USER CODE END 1 */

  /* MCU Configuration--------------------------------------------------------*/

  /* Reset of all peripherals, Initializes the Flash interface and the Systick. */
  HAL_Init();

  /* USER CODE BEGIN Init */

  /* USER CODE END Init */

  /* Configure the system clock */
  SystemClock_Config();

  /* USER CODE BEGIN SysInit */

  /* USER CODE END SysInit */

  /* Initialize all configured peripherals */
  MX_GPIO_Init();
  MX_CRC_Init();
  MX_USART3_UART_Init();
  MX_USART2_UART_Init();
  /* USER CODE BEGIN 2 */
if(HAL_GPIO_ReadPin(B1_GPIO_Port, B1_Pin) == GPIO_PIN_SET){

	printmsg("Entered UART read configuration\r\n");

	bootloader_uart_read_data();

}
else{

	printmsg("Entered to user application\r\n");

	bootloader_jump_to_user_app();

}
  /* USER CODE END 2 */

  /* Infinite loop */
  /* USER CODE BEGIN WHILE */
  while (1)
  {
    /* USER CODE END WHILE */

    /* USER CODE BEGIN 3 */
  }
  /* USER CODE END 3 */
}

/**
  * @brief System Clock Configuration
  * @retval None
  */
void SystemClock_Config(void)
{
  RCC_OscInitTypeDef RCC_OscInitStruct = {0};
  RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};

  /** Configure the main internal regulator output voltage
  */
  __HAL_RCC_PWR_CLK_ENABLE();
  __HAL_PWR_VOLTAGESCALING_CONFIG(PWR_REGULATOR_VOLTAGE_SCALE1);

  /** Initializes the RCC Oscillators according to the specified parameters
  * in the RCC_OscInitTypeDef structure.
  */
  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSI;
  RCC_OscInitStruct.HSIState = RCC_HSI_ON;
  RCC_OscInitStruct.HSICalibrationValue = RCC_HSICALIBRATION_DEFAULT;
  RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
  RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSI;
  RCC_OscInitStruct.PLL.PLLM = 8;
  RCC_OscInitStruct.PLL.PLLN = 50;
  RCC_OscInitStruct.PLL.PLLP = RCC_PLLP_DIV4;
  RCC_OscInitStruct.PLL.PLLQ = 7;
  if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK)
  {
    Error_Handler();
  }

  /** Initializes the CPU, AHB and APB buses clocks
  */
  RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK|RCC_CLOCKTYPE_SYSCLK
                              |RCC_CLOCKTYPE_PCLK1|RCC_CLOCKTYPE_PCLK2;
  RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
  RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV4;
  RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV2;

  if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_0) != HAL_OK)
  {
    Error_Handler();
  }
}

/**
  * @brief CRC Initialization Function
  * @param None
  * @retval None
  */
static void MX_CRC_Init(void)
{

  /* USER CODE BEGIN CRC_Init 0 */

  /* USER CODE END CRC_Init 0 */

  /* USER CODE BEGIN CRC_Init 1 */

  /* USER CODE END CRC_Init 1 */
  hcrc.Instance = CRC;
  if (HAL_CRC_Init(&hcrc) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN CRC_Init 2 */

  /* USER CODE END CRC_Init 2 */

}

/**
  * @brief USART2 Initialization Function
  * @param None
  * @retval None
  */
static void MX_USART2_UART_Init(void)
{

  /* USER CODE BEGIN USART2_Init 0 */

  /* USER CODE END USART2_Init 0 */

  /* USER CODE BEGIN USART2_Init 1 */

  /* USER CODE END USART2_Init 1 */
  huart2.Instance = USART2;
  huart2.Init.BaudRate = 115200;
  huart2.Init.WordLength = UART_WORDLENGTH_8B;
  huart2.Init.StopBits = UART_STOPBITS_1;
  huart2.Init.Parity = UART_PARITY_NONE;
  huart2.Init.Mode = UART_MODE_TX_RX;
  huart2.Init.HwFlowCtl = UART_HWCONTROL_NONE;
  huart2.Init.OverSampling = UART_OVERSAMPLING_16;
  if (HAL_UART_Init(&huart2) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN USART2_Init 2 */

  /* USER CODE END USART2_Init 2 */

}

/**
  * @brief USART3 Initialization Function
  * @param None
  * @retval None
  */
static void MX_USART3_UART_Init(void)
{

  /* USER CODE BEGIN USART3_Init 0 */

  /* USER CODE END USART3_Init 0 */

  /* USER CODE BEGIN USART3_Init 1 */

  /* USER CODE END USART3_Init 1 */
  huart3.Instance = USART3;
  huart3.Init.BaudRate = 115200;
  huart3.Init.WordLength = UART_WORDLENGTH_8B;
  huart3.Init.StopBits = UART_STOPBITS_1;
  huart3.Init.Parity = UART_PARITY_NONE;
  huart3.Init.Mode = UART_MODE_TX_RX;
  huart3.Init.HwFlowCtl = UART_HWCONTROL_NONE;
  huart3.Init.OverSampling = UART_OVERSAMPLING_16;
  if (HAL_UART_Init(&huart3) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN USART3_Init 2 */

  /* USER CODE END USART3_Init 2 */

}

/**
  * @brief GPIO Initialization Function
  * @param None
  * @retval None
  */
static void MX_GPIO_Init(void)
{
  GPIO_InitTypeDef GPIO_InitStruct = {0};
  /* USER CODE BEGIN MX_GPIO_Init_1 */

  /* USER CODE END MX_GPIO_Init_1 */

  /* GPIO Ports Clock Enable */

  __HAL_RCC_GPIOA_CLK_ENABLE();
  __HAL_RCC_GPIOB_CLK_ENABLE();
  __HAL_RCC_GPIOD_CLK_ENABLE();

  /*Configure GPIO pin : B1_Pin */
  GPIO_InitStruct.Pin = B1_Pin;
  GPIO_InitStruct.Mode = GPIO_MODE_IT_RISING;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  HAL_GPIO_Init(B1_GPIO_Port, &GPIO_InitStruct);

  /*Configure GPIO pins : LD4_Pin LD3_Pin LD5_Pin LD6_Pin
                           Audio_RST_Pin */
  GPIO_InitStruct.Pin = LD4_Pin|LD3_Pin|LD5_Pin|LD6_Pin;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(GPIOD, &GPIO_InitStruct);
  /* USER CODE BEGIN MX_GPIO_Init_2 */
  GPIO_InitStruct.Pin = B1_Pin;
  GPIO_InitStruct.Mode = GPIO_MODE_INPUT;
  GPIO_InitStruct.Pull = GPIO_PULLDOWN;
  HAL_GPIO_Init(B1_GPIO_Port, &GPIO_InitStruct);
  /* USER CODE END MX_GPIO_Init_2 */
}

/* USER CODE BEGIN 4 */

static void printmsg(char *formate,...){

#ifdef PRINTF

char str[80];

va_list args;
va_start(args, formate);
vsprintf(str, formate, args);
HAL_UART_Transmit(D_UART, (uint8_t*)str, strlen(str), HAL_MAX_DELAY);
va_end(args);

#endif

}

static void bootloader_uart_read_data(){

uint8_t BL_STACK_LEN = 0;
while(1){

HAL_UART_Receive(C_UART, &BL_FULL_STACK[0], 1, HAL_MAX_DELAY);
BL_STACK_LEN = BL_FULL_STACK[0];

if (BL_STACK_LEN == 0 || BL_STACK_LEN > 249) {
	printmsg("BL ERROR: Invalid packet length %d\r\n", BL_STACK_LEN);
	continue;
}

HAL_UART_Receive(C_UART, &BL_FULL_STACK[1], BL_STACK_LEN, HAL_MAX_DELAY);

switch (BL_FULL_STACK[1]) {
	case BL_GET_VER:

		bl_get_version(BL_FULL_STACK);

		break;
	case BL_GET_HELP:

		bl_get_help(BL_FULL_STACK);

			break;
	case BL_GET_CID:

		bl_get_CID(BL_FULL_STACK);

			break;
	case BL_GET_RPD_STATUS:

		bl_get_read_protection_level(BL_FULL_STACK);

			break;
	case BL_GO_TO_ADDR:

		bl_go_to_address(BL_FULL_STACK);

			break;
	case BL_FLASH_ERASE:

		bl_erase_flash(BL_FULL_STACK);

				break;
	case BL_MEM_WRITE:

		bl_memory_write(BL_FULL_STACK);

				break;
	case BL_MEM_READ:

		bl_memory_read(BL_FULL_STACK);

		break;
	case BL_EN_R_W_PROTECT:

		bl_en_read_write_protection(BL_FULL_STACK);

				break;
	case BL_READ_SECTOR_STATUS:

		bl_get_read_sector_protection_status(BL_FULL_STACK);

				break;
	case BL_OTP_READ:

		read_otp_content(BL_FULL_STACK);

				break;
	case BL_DIS_R_RW_PROTECT:


		bl_diable_read_write_protection(BL_FULL_STACK);

				break;
	default:

		printmsg("INVALID COMMAND CODE\r\n");

		break;
		}


	}

}

static void bootloader_jump_to_user_app(){

	void (*app_reset_handler)(void);

	uint32_t msp_value = *((volatile uint32_t*)(SECTOR2_FLASH_STORAGE));

	printmsg("BL DEBUG MSG:MSP ADDR: %#x\r\n", msp_value);

	uint32_t reset_handler_addr = *((volatile uint32_t*)(SECTOR2_FLASH_STORAGE + 4));

	app_reset_handler = (void*) reset_handler_addr;

	printmsg("BL DEBUG MSG:RST HANDLER ADDR: %#x\r\n", app_reset_handler);

	/* Validate application vector table before jumping */
	if (msp_value == 0xFFFFFFFF || msp_value == 0x00000000) {
		printmsg("BL ERROR: Invalid MSP - no app found at 0x%08lx\r\n", (unsigned long)SECTOR2_FLASH_STORAGE);
		return;
	}

	if (reset_handler_addr == 0xFFFFFFFF || reset_handler_addr == 0x00000000) {
		printmsg("BL ERROR: Invalid reset handler - no app found\r\n");
		return;
	}

	if ((reset_handler_addr & 0xFF000000) != 0x08000000) {
		printmsg("BL ERROR: Reset handler 0x%08lx not in flash range\r\n", (unsigned long)reset_handler_addr);
		return;
	}

	printmsg("BL DEBUG MSG: Jumping to application...\r\n");

	/* Ensure last UART TX completes before deinit */
	HAL_Delay(10);

	/* Disable all interrupts - critical for safe transition */
	__disable_irq();

	/* Stop SysTick - it keeps firing if left running, but app uses TIM6 */
	SysTick->CTRL = 0;
	SysTick->LOAD = 0;
	SysTick->VAL = 0;

	/* Clear all pending interrupts in NVIC */
	for (int i = 0; i < 8; i++) {
		NVIC->ICER[i] = 0xFFFFFFFF;
		NVIC->ICPR[i] = 0xFFFFFFFF;
	}

	/* Deinitialize all HAL peripherals */
	HAL_DeInit();

	/* Reset Clock Configuration to default HSI state manually since HAL_RCC_DeInit is a no-op on STM32F4 */
	RCC->CR |= RCC_CR_HSION;
	while ((RCC->CR & RCC_CR_HSIRDY) == 0);

	RCC->CFGR = 0x00000000;
	while ((RCC->CFGR & RCC_CFGR_SWS) != 0);

	RCC->CR &= ~(RCC_CR_HSEON | RCC_CR_HSEBYP | RCC_CR_CSSON | RCC_CR_PLLON | RCC_CR_PLLI2SON);
	while ((RCC->CR & RCC_CR_PLLRDY) != 0);
	while ((RCC->CR & RCC_CR_PLLI2SRDY) != 0);

	RCC->PLLCFGR = 0x24003010;
	RCC->CIR = 0x00000000;

	/* Reset Flash Latency to 0 wait states (safe at 16MHz) */
	FLASH->ACR &= ~FLASH_ACR_LATENCY;

	/* Set VTOR to application's vector table so any interrupt uses app handlers */
	SCB->VTOR = SECTOR2_FLASH_STORAGE;
	__DSB();  /* Ensure VTOR write completes before any interrupt can fire */
	__ISB();  /* Flush pipeline so new vector table is used immediately */

	/* Update SystemCoreClock to match actual clock (HSI 16MHz after RCC_DeInit) */
	SystemCoreClockUpdate();

	/* Disable EXTI line 0 and clear pending (button B1 configured as IT_RISING) */
	EXTI->IMR &= ~EXTI_IMR_MR0;
	EXTI->PR = EXTI_PR_PR0;

	/* Re-enable global interrupts - all sources are stopped, NVIC is clean */
	__enable_irq();

	/* Set stack pointer to application's initial SP value */
	__set_MSP(msp_value);

	/* Jump to application reset handler - never returns */
	app_reset_handler();

}

void bl_get_version(uint8_t* pSTACK){
	uint8_t bl_version = 0;
	printmsg("BL DEBUG MSG : Getting Boot-Loader version...\r\n");

	uint8_t cmd_packet_len = pSTACK[0] + 1;  // 6
	uint32_t host_crc = *((uint32_t*)(pSTACK + cmd_packet_len - 4)); // 6-4 = 2

	if(bootloader_verify_crc(&pSTACK[0], cmd_packet_len-4, host_crc)){

		 bl_version = get_booloader_ver();
		 bootloader_send_ack(pSTACK[1], 1);
		 printmsg("BL DEBUG: Boot-Loader Version - %d %#x\r\n",bl_version,bl_version);
		 bootloader_uart_write_data(&bl_version, 1);

	}
	else{

		 printmsg("BL DEBUG MSG : Boot-Loader CHECKSUM Failed !\r\n");
		 bootloader_send_nack();

	}

}

void bl_get_help(uint8_t* pSTACK){

	printmsg("BL DEBUG MSG : Getting Help Status...\r\n");

		uint8_t cmd_packet_len = pSTACK[0] + 1;  // 6
		uint32_t host_crc = *((uint32_t*)(pSTACK + cmd_packet_len - 4)); // 6-4 = 2

		if(bootloader_verify_crc(&pSTACK[0], cmd_packet_len-4, host_crc)){

			 bootloader_send_ack(pSTACK[1], sizeof(HELP_CODE));
			 bootloader_uart_write_data(&HELP_CODE[0], sizeof(HELP_CODE));

		}
		else{

			 printmsg("BL DEBUG MSG : Boot-Loader CHECKSUM Failed !\r\n");
			 bootloader_send_nack();

		}

}

void bl_get_CID(uint8_t* pSTACK){
	uint16_t mcu_cid = 0;
	printmsg("BL DEBUG MSG : Getting MCU Chip ID...\r\n");

	uint8_t cmd_packet_len = pSTACK[0] + 1;  // 6
	uint32_t host_crc = *((uint32_t*)(pSTACK + cmd_packet_len - 4)); // 6-4 = 2

	if(bootloader_verify_crc(&pSTACK[0], cmd_packet_len-4, host_crc)){

		 mcu_cid = get_mcu_cid();
		 bootloader_send_ack(pSTACK[1], 2);
		 printmsg("BL DEBUG: MCU Chip ID - %d %#x\r\n",mcu_cid,mcu_cid);
		 bootloader_uart_write_data((uint8_t*)&mcu_cid, 2);

	}
	else{

		 printmsg("BL DEBUG MSG : Boot-Loader CHECKSUM Failed !\r\n");
		 bootloader_send_nack();

	}


}

void bl_get_read_protection_level(uint8_t* pSTACK){

	uint8_t rdp_level = 0;
	printmsg("BL DEBUG MSG : Getting RDP Protection Level Status...\r\n");

	uint8_t cmd_packet_len = pSTACK[0] + 1;  // 6
	uint32_t host_crc = *((uint32_t*)(pSTACK + cmd_packet_len - 4)); // 6-4 = 2

	if(bootloader_verify_crc(&pSTACK[0], cmd_packet_len-4, host_crc)){

		 rdp_level = get_rdp_level();
		 bootloader_send_ack(pSTACK[1], 1);
		 printmsg("BL DEBUG: RDP Level - %d %#x\r\n",rdp_level,rdp_level);
		 bootloader_uart_write_data(&rdp_level, 1);

	}
	else{

		 printmsg("BL DEBUG MSG : Boot-Loader CHECKSUM Failed !\r\n");
		 bootloader_send_nack();

	}

}


void bl_go_to_address(uint8_t* pSTACK){

	uint32_t extract_mem = 0;
    uint8_t valid_addr = VALID_ADDR;
    uint8_t invalid_addr = INVALID_ADDR;

	printmsg("BL DEBUG MSG : Going to the said memory address...\r\n");
	uint8_t cmd_packet_len = pSTACK[0] + 1;  // 6
	uint32_t host_crc = *((uint32_t*)(pSTACK + cmd_packet_len - 4)); // 6-4 = 2

	if(bootloader_verify_crc(&pSTACK[0], cmd_packet_len-4, host_crc)){

		 bootloader_send_ack(pSTACK[1], 1);
		 extract_mem = *((uint32_t*)&pSTACK[2]);

		if(validate_addr(extract_mem) == VALID_ADDR){

			 printmsg("BL DEBUG:GO ADDR IS VALID - %#x\r\n",extract_mem);
			 bootloader_uart_write_data(&valid_addr, 1);

			 /* If jumping to application region, read MSP from vector table */
			 uint32_t msp_value = 0;
			 if (extract_mem >= SECTOR2_FLASH_STORAGE && extract_mem < FLASH_EN) {
				 msp_value = *((volatile uint32_t*)(SECTOR2_FLASH_STORAGE));
				 printmsg("BL DEBUG: Will set MSP to 0x%08lx before jump\r\n", (unsigned long)msp_value);
			 }

			 /* Check if Thumb bit (LSB) is already set, if not add +1 for Thumb mode */
			 if ((extract_mem & 0x1) == 0) {
				 extract_mem += 1;  /* Even address - add Thumb bit */
				 printmsg("BL DEBUG: Added Thumb bit, jumping to 0x%08lx\r\n", (unsigned long)extract_mem);
			 } else {
				 printmsg("BL DEBUG: Thumb bit already set, jumping to 0x%08lx\r\n", (unsigned long)extract_mem);
			 }

			 void (*jump_addr) (void) = (void*)extract_mem;

			 /* Ensure last UART TX completes before deinit */
			 HAL_Delay(10);

			 /* Disable all interrupts - critical for safe transition */
			 __disable_irq();

			 /* Stop SysTick - it keeps firing if left running */
			 SysTick->CTRL = 0;
			 SysTick->LOAD = 0;
			 SysTick->VAL = 0;

			 /* Clear all pending interrupts in NVIC */
			 for (int i = 0; i < 8; i++) {
				 NVIC->ICER[i] = 0xFFFFFFFF;
				 NVIC->ICPR[i] = 0xFFFFFFFF;
			 }

			 /* Deinitialize all HAL peripherals */
			 HAL_DeInit();

			 /* Reset Clock Configuration to default HSI state manually since HAL_RCC_DeInit is a no-op on STM32F4 */
			 RCC->CR |= RCC_CR_HSION;
			 while ((RCC->CR & RCC_CR_HSIRDY) == 0);

			 RCC->CFGR = 0x00000000;
			 while ((RCC->CFGR & RCC_CFGR_SWS) != 0);

			 RCC->CR &= ~(RCC_CR_HSEON | RCC_CR_HSEBYP | RCC_CR_CSSON | RCC_CR_PLLON | RCC_CR_PLLI2SON);
			 while ((RCC->CR & RCC_CR_PLLRDY) != 0);
			 while ((RCC->CR & RCC_CR_PLLI2SRDY) != 0);

			 RCC->PLLCFGR = 0x24003010;
			 RCC->CIR = 0x00000000;

			 /* Reset Flash Latency to 0 wait states (safe at 16MHz) */
			 FLASH->ACR &= ~FLASH_ACR_LATENCY;

			 /* If jumping to application flash region, set VTOR to application base */
			 if ((extract_mem-1) >= SECTOR2_FLASH_STORAGE && (extract_mem-1) < FLASH_EN) {
				 SCB->VTOR = SECTOR2_FLASH_STORAGE;  /* Always point to app vector table base */
				 __DSB();
				 __ISB();
			 }

			 /* Update SystemCoreClock to match actual clock (HSI 16MHz after RCC reset) */
			 SystemCoreClockUpdate();

			 /* Disable EXTI line 0 and clear pending (button B1 configured as IT_RISING) */
			 EXTI->IMR &= ~EXTI_IMR_MR0;
			 EXTI->PR = EXTI_PR_PR0;

			 /* Re-enable global interrupts - all sources are stopped, NVIC is clean */
			 __enable_irq();

			 /* Set MSP from vector table if we read it earlier */
			 if (msp_value != 0) {
				 __set_MSP(msp_value);
			 }

			 /* Jump to address - never returns */
			 jump_addr();
		}
		else {

			 bootloader_send_ack(pSTACK[1], 1);
			 printmsg("BL DEBUG:GO ADDR IS INVALID WHICH IS - %#x\r\n",extract_mem);
			 bootloader_uart_write_data(&invalid_addr, 1);
		}

	}
	else{

		 printmsg("BL DEBUG MSG : Boot-Loader CHECKSUM Failed !\r\n");
		 bootloader_send_nack();

	}

}



void bl_erase_flash(uint8_t* pSTACK){

	uint8_t erase_status = 0x00;
	printmsg("BL DEBUG MSG : Triggered Erasing...\r\n");

	uint8_t cmd_packet_len = pSTACK[0] + 1;  // 6
	uint32_t host_crc = *((uint32_t*)(pSTACK + cmd_packet_len - 4)); // 6-4 = 2

	if(bootloader_verify_crc(&pSTACK[0], cmd_packet_len-4, host_crc)){

		 HAL_GPIO_WritePin(GPIOD, LD4_Pin, GPIO_PIN_SET);
		 erase_status = execute_erase_task(pSTACK[2], pSTACK[3]);
		 HAL_GPIO_WritePin(GPIOD, LD4_Pin, GPIO_PIN_RESET);

		 bootloader_send_ack(pSTACK[1], 1);
		 printmsg("BL DEBUG: ERASE STATUS - %#x\r\n",erase_status);
		 bootloader_uart_write_data(&erase_status, 1);

	}
	else{

		 printmsg("BL DEBUG MSG : Boot-Loader CHECKSUM Failed !\r\n");
		 bootloader_send_nack();

	}

}

void bl_memory_write(uint8_t* pSTACK){


	uint8_t write_status = 0x00;
    uint8_t invalid_addr = INVALID_ADDR;
    uint8_t payload_len = pSTACK[6];
    uint32_t base_mem_addr = 0;

    base_mem_addr = *( (uint32_t*)&pSTACK[2] );

		printmsg("BL DEBUG MSG : Triggered Flashing...\r\n");

		uint8_t cmd_packet_len = pSTACK[0] + 1;  // 6
		uint32_t host_crc = *((uint32_t*)(pSTACK + cmd_packet_len - 4)); // 6-4 = 2

		if(bootloader_verify_crc(&pSTACK[0], cmd_packet_len-4, host_crc)){

			if(validate_addr(base_mem_addr) == VALID_ADDR){

			 HAL_GPIO_WritePin(GPIOD, LD4_Pin, GPIO_PIN_SET);
			 write_status = execute_write_task(base_mem_addr, &pSTACK[7], payload_len);
			 HAL_GPIO_WritePin(GPIOD, LD4_Pin, GPIO_PIN_RESET);

			 bootloader_send_ack(pSTACK[1], 1);
			 printmsg("BL DEBUG: WRITE STATUS - %#x\r\n",write_status);
			 bootloader_uart_write_data(&write_status, 1);

			}
			else {

				 bootloader_send_ack(pSTACK[1], 1);
				 printmsg("BL DEBUG:GO ADDR IS INVALID WHICH IS- %#x\r\n",base_mem_addr);
				 bootloader_uart_write_data(&invalid_addr, 1);
			}

		}
		else{

			 printmsg("BL DEBUG MSG : Boot-Loader CHECKSUM Failed !\r\n");
			 bootloader_send_nack();

		}


}

void bl_memory_read(uint8_t* pSTACK){

	uint32_t read_mem_addr = 0;
	uint8_t read_len = 0;
	uint8_t invalid_addr = INVALID_ADDR;

	printmsg("BL DEBUG MSG : Memory read requested...\r\n");

	uint8_t cmd_packet_len = pSTACK[0] + 1;
	uint32_t host_crc = *((uint32_t*)(pSTACK + cmd_packet_len - 4));

	if(bootloader_verify_crc(&pSTACK[0], cmd_packet_len - 4, host_crc)){

		read_mem_addr = *((uint32_t*)&pSTACK[2]);
		read_len = pSTACK[6];

		if(validate_addr(read_mem_addr) == VALID_ADDR){
			printmsg("BL DEBUG: Read addr valid - %#x, len=%d\r\n", read_mem_addr, read_len);

			if(read_len == 0 || read_len > 128){
				printmsg("BL DEBUG: Invalid read length %d\r\n", read_len);
				bootloader_send_ack(pSTACK[1], 1);
				uint8_t err_len = 0xFF;
				bootloader_uart_write_data(&err_len, 1);
				return;
			}

			bootloader_send_ack(pSTACK[1], read_len);
			bootloader_uart_write_data((uint8_t*)read_mem_addr, read_len);
			printmsg("BL DEBUG: Memory read done\r\n");
		}
		else{
			printmsg("BL DEBUG: Read addr INVALID - %#x\r\n", read_mem_addr);
			bootloader_send_ack(pSTACK[1], 1);
			bootloader_uart_write_data(&invalid_addr, 1);
		}
	}
	else{
		printmsg("BL DEBUG MSG : Boot-Loader CHECKSUM Failed !\r\n");
		bootloader_send_nack();
	}
}

void bl_en_read_write_protection(uint8_t* pSTACK){

	uint8_t status = 0x00;
	printmsg("BL DEBUG MSG : Enabling R/W Protection...\r\n");

	uint8_t cmd_packet_len = pSTACK[0] + 1;  // 6
	uint32_t host_crc = *((uint32_t*)(pSTACK + cmd_packet_len - 4)); // 6-4 = 2

	if(bootloader_verify_crc(&pSTACK[0], cmd_packet_len-4, host_crc)){

		  // Validate protection mode (1=WRP, 2=PCROP)
		    if(pSTACK[3] != 1 && pSTACK[3] != 2){
		        printmsg("BL ERROR: Invalid protection mode %d\r\n", pSTACK[3]);
		        bootloader_send_nack();
		        return;
		    }

		    // Prevent protecting bootloader sectors 0-1
		    if(pSTACK[2] & 0x03){
		        printmsg("BL ERROR: Cannot protect bootloader sectors\r\n");
		        bootloader_send_nack();
		        return;
		    }
		 status = sector_status(pSTACK[2], pSTACK[3], 0);


		 bootloader_send_ack(pSTACK[1], 1);
		 printmsg("BL DEBUG: SECTOR STATUS - %#x\r\n",status);
		 bootloader_uart_write_data(&status, 1);

	}
	else{

		 printmsg("BL DEBUG MSG : Boot-Loader CHECKSUM Failed !\r\n");
		 bootloader_send_nack();

	}


}

void bl_diable_read_write_protection(uint8_t* pSTACK){

	uint8_t status = 0x00;
		printmsg("BL DEBUG MSG : Disabling R/W Protection...\r\n");

		uint8_t cmd_packet_len = pSTACK[0] + 1;  // 6
		uint32_t host_crc = *((uint32_t*)(pSTACK + cmd_packet_len - 4)); // 6-4 = 2

		if(bootloader_verify_crc(&pSTACK[0], cmd_packet_len-4, host_crc)){

			 // Prevent protecting bootloader sectors 0-1
		  if(pSTACK[2] & 0x03){
			  printmsg("BL ERROR: Cannot protect bootloader sectors\r\n");
			  bootloader_send_nack();
			  return;
			 }
			 status = sector_status(pSTACK[2], 0, 1);


			 bootloader_send_ack(pSTACK[1], 1);
			 printmsg("BL DEBUG: SECTOR STATUS - %#x\r\n",status);
			 bootloader_uart_write_data(&status, 1);

		}
		else{

			 printmsg("BL DEBUG MSG : Boot-Loader CHECKSUM Failed !\r\n");
			 bootloader_send_nack();

		}



}

void bl_get_read_sector_protection_status(uint8_t* pSTACK){ //


	uint16_t protection_status = 0;
	printmsg("BL DEBUG MSG :  Reading Sector Protection Status...\r\n");

	uint8_t cmd_packet_len = pSTACK[0] + 1;  // 6
	uint32_t host_crc = *((uint32_t*)(pSTACK + cmd_packet_len - 4)); // 6-4 = 2

	if(bootloader_verify_crc(&pSTACK[0], cmd_packet_len-4, host_crc)){

        volatile uint32_t *pOPTCR = (uint32_t*) 0x40023C14 ;
        protection_status = (*pOPTCR >> 16) & 0xFFF;


		 bootloader_send_ack(pSTACK[1], 2);
		 printmsg("BL DEBUG: Protection Status - 0x%04X\r\n",protection_status);
		 uint8_t status_byte[2] = { 0 };
		 status_byte[0] = (uint8_t)(protection_status & 0xFFU);
		 status_byte[1] = (uint8_t)((protection_status >> 8) & 0x0FU);
		 bootloader_uart_write_data(&status_byte[0], 2);

	}
	else{

		 printmsg("BL DEBUG MSG : Boot-Loader CHECKSUM Failed !\r\n");
		 bootloader_send_nack();

	}



}

void read_otp_content(uint8_t* pSTACK){

	uint32_t read_otp_addr = 0;
		uint8_t read_len = 0;
		uint8_t invalid_addr = INVALID_ADDR;

		printmsg("BL DEBUG MSG : OTP read requested...\r\n");

		uint8_t cmd_packet_len = pSTACK[0] + 1;
		uint32_t host_crc = *((uint32_t*)(pSTACK + cmd_packet_len - 4));

		if(bootloader_verify_crc(&pSTACK[0], cmd_packet_len - 4, host_crc)){

			read_otp_addr = *((uint32_t*)&pSTACK[2]);
			read_len = pSTACK[6];

			if(validate_addr(read_otp_addr) == VALID_ADDR){
				printmsg("BL DEBUG: otp addr is valid - %#x, len=%d\r\n", read_otp_addr, read_len);

				if(read_len == 0 || read_len > 128){
					printmsg("BL DEBUG: Invalid otp read length %d\r\n", read_len);
					bootloader_send_ack(pSTACK[1], 1);
					uint8_t err_len = 0xFF;
					bootloader_uart_write_data(&err_len, 1);
					return;
				}

				bootloader_send_ack(pSTACK[1], read_len);
				bootloader_uart_write_data((uint8_t*)read_otp_addr, read_len);
				printmsg("BL DEBUG: Memory read done\r\n");
			}
			else{
				printmsg("BL DEBUG: Read otp addr is INVALID - %#x\r\n", read_otp_addr);
				bootloader_send_ack(pSTACK[1], 1);
				bootloader_uart_write_data(&invalid_addr, 1);
			}
		}
		else{
			printmsg("BL DEBUG MSG : Boot-Loader CHECKSUM Failed !\r\n");
			bootloader_send_nack();
		}
	}



static void bootloader_send_ack(uint8_t cmd_code, uint8_t follow_len){

uint8_t ack_buf[2];
ack_buf[0] = BL_ACK;
ack_buf[1] = follow_len;
HAL_UART_Transmit(C_UART, ack_buf, 2, HAL_MAX_DELAY);


}

static void bootloader_send_nack(void){


uint8_t nack = BL_NACK;
HAL_UART_Transmit(C_UART, &nack, 1, HAL_MAX_DELAY);


}

static uint8_t bootloader_verify_crc(uint8_t* pSTACK, uint8_t len, uint32_t host_crc){

   __HAL_CRC_DR_RESET(&hcrc);
   uint32_t mcu_crc = 0;

   for(int i = 0; i < len; i++){

	   uint32_t i_data =  pSTACK[i];
	   mcu_crc = HAL_CRC_Accumulate(&hcrc, &i_data, 1);

   }
   if(host_crc == mcu_crc){
	   return CRC_SUCCESS;
   }
	   return CRC_FAIL;


}

static void bootloader_uart_write_data(uint8_t* pBuffer, uint8_t len){

	HAL_UART_Transmit(C_UART, pBuffer, len, HAL_MAX_DELAY);

}

static uint8_t get_booloader_ver(){

return (uint8_t)BL_VER;
}

static uint16_t get_mcu_cid(){

	uint16_t cid = 0;
	cid = (uint16_t)(DBGMCU->IDCODE & 0x0FFFU);
	return cid;
}

static uint8_t get_rdp_level(){
	uint8_t rdp_level = 0;

#if OB_HAL

FLASH_OBProgramInitTypeDef OB_handel = {0};
HAL_FLASHEx_OBGetConfig(&OB_handel);
rdp_level = (uint8_t) OB_handel.RDPLevel;


#else

	uint32_t pRDP = (*((volatile uint32_t*)0x1FFFC000U) >> 8);
//	volatile uint32_t *pRDP = (uint32_t*)0x1FFFC000U;
//	rdp_level = (uint8_t)(*pRDP >> 8);
	rdp_level = (uint8_t) pRDP;

#endif

	return rdp_level;
}

static uint8_t validate_addr(uint32_t addr){

	if(addr >= SRAM1_BASE && addr <= SRAM1_END){

		return VALID_ADDR;

	}
	else if (addr >= SRAM2_BASE && addr <= SRAM2_END) {

		return VALID_ADDR;

	}
	else if (addr >= FLASH_BASE && addr <= FLASH_EN) {

		return VALID_ADDR;

	}
	else if (addr >= BKPSRAM_BASE && addr <= BKPSRAM_END) {

		return VALID_ADDR;

	}
	else if (addr >= FLASH_OTP_BASE && addr <= OTP_END) {

		return VALID_ADDR;

	}
	else{

		return INVALID_ADDR;

	}

}

static uint8_t execute_erase_task(uint8_t sector_number, uint8_t number_of_sector){

uint32_t SectorError;
FLASH_EraseInitTypeDef herase;
HAL_StatusTypeDef rStatus;

  	  if(number_of_sector > 12)
  		  return INVALID_SECTOR;

	if(sector_number == 0xFFU || sector_number <= 11){

		if(sector_number == 0xFFU){

			herase.TypeErase = FLASH_TYPEERASE_MASSERASE;

		}
		else{
			uint8_t remaining_sector = 12 - sector_number;
			if(number_of_sector > remaining_sector){

				number_of_sector = remaining_sector;

			}
			herase.TypeErase = FLASH_TYPEERASE_SECTORS;
			herase.Sector = sector_number;
			herase.NbSectors = number_of_sector;

		}
		herase.Banks = FLASH_BANK_1;
        herase.VoltageRange = FLASH_VOLTAGE_RANGE_3;

        HAL_FLASH_Unlock();
		rStatus = (HAL_StatusTypeDef)HAL_FLASHEx_Erase(&herase, &SectorError);
		HAL_FLASH_Lock();

		return rStatus;

		}

return INVALID_SECTOR;
}

static uint8_t execute_write_task(uint32_t base_mem_addr, uint8_t *pBuffer, uint32_t payload_len){

	HAL_StatusTypeDef status = HAL_OK;

    HAL_FLASH_Unlock();

	for(uint32_t i = 0; i < payload_len; i++){

	    status = HAL_FLASH_Program(FLASH_TYPEPROGRAM_BYTE, base_mem_addr + i, pBuffer[i]);

	}
	HAL_FLASH_Lock();

	return status;

}

static uint8_t sector_status(uint8_t sector_view, uint8_t protection_mode, uint8_t disable){

	volatile uint32_t *pOPTCR = (uint32_t*) 0x40023C14;

	if(protection_mode == (uint8_t) 1){
    HAL_FLASH_OB_Unlock();

    while(__HAL_FLASH_GET_FLAG(FLASH_FLAG_BSY) != RESET);
    *pOPTCR &= ~(1 << 31);

    *pOPTCR &= ~(sector_view << 16);

    *pOPTCR |= (1 << 1);
    while(__HAL_FLASH_GET_FLAG(FLASH_FLAG_BSY) != RESET)
    	;

	HAL_FLASH_OB_Lock();

	return 1;
	}

	if(protection_mode == (uint8_t) 2){
    HAL_FLASH_OB_Unlock();

    while(__HAL_FLASH_GET_FLAG(FLASH_FLAG_BSY) != RESET);
    *pOPTCR |= (1 << 31);

    *pOPTCR &= ~(0xFFU << 16);
    *pOPTCR |= (sector_view << 16);

    *pOPTCR |= (1 << 1);
    while(__HAL_FLASH_GET_FLAG(FLASH_FLAG_BSY) != RESET);

    HAL_FLASH_OB_Lock();

    return 2;

	}

	if(disable){

	    HAL_FLASH_OB_Unlock();

	    while(__HAL_FLASH_GET_FLAG(FLASH_FLAG_BSY) != RESET);
	    *pOPTCR |= (1 << 31);

	    *pOPTCR |= (0xFFU << 16);

	    *pOPTCR |= (1 << 1);
	    while(__HAL_FLASH_GET_FLAG(FLASH_FLAG_BSY) != RESET)
	    	;

		HAL_FLASH_OB_Lock();

	}

    return 0;
}

/* USER CODE END 4 */

/**
  * @brief  This function is executed in case of error occurrence.
  * @retval None
  */
void Error_Handler(void)
{
  /* USER CODE BEGIN Error_Handler_Debug */
  /* User can add his own implementation to report the HAL error return state */
  __disable_irq();
  while (1)
  {
  }
  /* USER CODE END Error_Handler_Debug */
}

#ifdef  USE_FULL_ASSERT
/**
  * @brief  Reports the name of the source file and the source line number
  *         where the assert_param error has occurred.
  * @param  file: pointer to the source file name
  * @param  line: assert_param error line source number
  * @retval None
  */
void assert_failed(uint8_t *file, uint32_t line)
{
  /* USER CODE BEGIN 6 */
  /* User can add his own implementation to report the file name and line number,
     ex: printf("Wrong parameters value: file %s on line %d\r\n", file, line) */
  /* USER CODE END 6 */
}
#endif /* USE_FULL_ASSERT */
