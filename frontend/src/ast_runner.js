const ASTProcessor = require('./tools/ast/ASTProcessor');
const types = require('@babel/types');

const processor = new ASTProcessor();
processor.process({
   inputPath: './static/ast/demos/origin.js',
    outputPath: './static/ast/demos/target.js',
    visitors: [
        {
            VariableDeclaration(path) {
                // 如果变量名是a，则插入一个变量b
                if (path.node.declarations[0].id.name === 'a') {
                    let left = types.binaryExpression("*", types.identifier("a"), types.numericLiteral(5))
                    let right = types.numericLiteral(1)
                    let init = types.binaryExpression("+", left, right)
                    let declarator = types.variableDeclarator(types.identifier("b"), init)
                    let declaration = types.variableDeclaration("const", [declarator])
                    path.insertAfter(declaration)
                }
            },
            //  Unicode 编码，字符串还原
            StringLiteral(path) {
                // 以下方法均可
                // path.node.extra.raw = path.node.rawValue
                // path.node.extra.raw = '"' + path.node.value + '"'
                // delete path.node.extra
                if (path.node.extra) {
                    delete path.node.extra.raw
                }
            },
            "BinaryExpression|CallExpression|ConditionalExpression"(path) {
                try {
                    const {confident, value} = path.evaluate()
                    if (confident) {
                        path.replaceInline(types.valueToNode(value))
                    }
                } catch (error) {
                    console.log(error)
                }
            }
        },
    ]
}).then(result => {
    if (result.success) {
        console.log('处理成功:', result);
    } else {
        console.error('处理失败:', result.error);
    }
}).catch(error => {
    console.error('处理过程中发生错误:', error);
});