const fs = require('fs');
const path = require('path');
const parser = require('@babel/parser');
const traverser = require('@babel/traverse');
const generater = require('@babel/generator');


class ASTProcessor {
    constructor(options = {}) {
        this.options = {
            parserOptions: {
                sourceType: 'module',
                allowImportExportEverywhere: true,
                allowReturnOutsideFunction: true,
                plugins: [
                    'jsx',
                    'typescript',
                    'decorators-legacy',
                    'classProperties',
                    'asyncGenerators',
                    'functionBind',
                    'exportDefaultFrom',
                    'exportNamespaceFrom',
                    'dynamicImport',
                    'nullishCoalescingOperator',
                    'optionalChaining'
                ]
            },
            // 默认生成选项
            generatorOptions: {
                compact: false,
                comments: true,
                retainLines: false
            },
            ...options
        };
    }

    /**
     * 读取文件（支持加密文件）
     * @param {string} filePath - 文件路径
     * @returns {Promise<string>} 文件内容
     */
    async readFile(filePath) {
        try {
            const data = await fs.promises.readFile(filePath);
            return data.toString('utf8');
        } catch (error) {
            throw new Error(`读取文件失败: ${error.message}`);
        }
    }

    /**
     * 解析代码为AST
     * @param {string} code - 源代码
     * @returns {Object} AST对象
     */
    parse(code) {
        try {
            return parser.parse(code, this.options.parserOptions);
        } catch (error) {
            throw new Error(`代码解析失败: ${error.message}`);
        }
    }

    /**
     * 遍历AST并应用visitor
     * @param {Object} ast - AST对象
     * @param {Object|Array} visitors - visitor对象或数组
     * @returns {Object} 处理后的AST
     */
    traverse(ast, visitors) {
        if (!visitors) {
            return ast;
        }

        // 支持多个visitor
        const visitorArray = Array.isArray(visitors) ? visitors : [visitors];

        visitorArray.forEach(visitor => {
            if (typeof visitor === 'function') {
                // 如果visitor是函数，则作为通用visitor处理
                traverser.default(ast, {
                    enter(path) {
                        visitor(path, 'enter');
                    },
                    exit(path) {
                        visitor(path, 'exit');
                    }
                });
            } else if (typeof visitor === 'object') {
                // 如果visitor是对象，直接使用
                traverser.default(ast, visitor);
            } else {
                throw new Error('Visitor必须是对象或函数');
            }
        });

        return ast;
    }

    /**
     * 将AST生成代码
     * @param {Object} ast - AST对象
     * @returns {string} 生成的代码
     */
    generate(ast) {
        try {
            const result = generater.generate(ast, this.options.generatorOptions);
            return result.code;
        } catch (error) {
            throw new Error(`代码生成失败: ${error.message}`);
        }
    }

    /**
     * 写入文件（支持加密）
     * @param {string} filePath - 文件路径
     * @param {string} content - 文件内容
     * @param {boolean} encrypt - 是否加密
     * @returns {Promise<void>}
     */
    async writeFile(filePath, content) {
        try {
            // 确保目录存在
            const dir = path.dirname(filePath);
            await fs.promises.mkdir(dir, {recursive: true});

            let data = content;
            await fs.promises.writeFile(filePath, data);
        } catch (error) {
            throw new Error(`写入文件失败: ${error.message}`);
        }
    }

    /**
     * 主要处理方法 - 处理加密文件并应用visitor
     * @param {Object} config - 配置对象
     * @param {string} config.inputPath - 输入文件路径
     * @param {string} config.outputPath - 输出文件路径
     * @param {Object|Array} config.visitors - visitor对象或数组
     * @param {boolean} config.isInputEncrypted - 输入文件是否加密
     * @param {boolean} config.encryptOutput - 是否加密输出文件
     * @returns {Promise<Object>} 处理结果
     */
    async process(config) {
        const {
            inputPath,
            outputPath,
            visitors,
        } = config;

        try {
            // 1. 读取文件
            console.log(`读取文件: ${inputPath}`);
            const sourceCode = await this.readFile(inputPath);

            // 2. 解析AST
            console.log('解析AST...');
            const ast = this.parse(sourceCode);

            // 3. 应用visitor
            if (visitors) {
                console.log('应用visitor...');
                this.traverse(ast, visitors);
            }

            // 4. 生成代码
            console.log('生成代码...');
            const transformedCode = this.generate(ast);

            // 5. 写入文件
            console.log(`写入文件: ${outputPath}`);
            await this.writeFile(outputPath, transformedCode);

            return {
                success: true,
                inputPath,
                outputPath,
                originalSize: sourceCode.length,
                transformedSize: transformedCode.length,
                ast
            };

        } catch (error) {
            return {
                success: false,
                error: error.message,
                inputPath,
                outputPath
            };
        }
    }

    /**
     * 批量处理文件
     * @param {Array} configs - 配置数组
     * @returns {Promise<Array>} 处理结果数组
     */
    async batchProcess(configs) {
        const results = [];

        for (const config of configs) {
            const result = await this.process(config);
            results.push(result);

            if (result.success) {
                console.log(`✓ 处理成功: ${config.inputPath} -> ${config.outputPath}`);
            } else {
                console.error(`✗ 处理失败: ${config.inputPath} - ${result.error}`);
            }
        }

        return results;
    }
}
// 导出ASTProcessor类
module.exports = ASTProcessor;
